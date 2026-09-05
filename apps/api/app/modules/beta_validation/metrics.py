from __future__ import annotations

import hashlib
import hmac
import math
import re
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.modules.beta_validation.schemas import (
    METRIC_DEFINITION_VERSION,
    NOTICE_VERSION,
    RETENTION_DAYS,
    BetaMetricDefinition,
    BetaMetricSnapshot,
    BetaMetricValue,
    BetaParticipantDeletion,
    BetaParticipantMetricExport,
    BetaTrustTier,
    BetaValidationObservation,
    BetaValidationParticipation,
    BetaValidationReceipt,
)


_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_TRUST_TIERS: tuple[BetaTrustTier, ...] = (
    "verified_source",
    "program_verified",
    "model_reviewed",
    "teacher_review_required",
)


class BetaValidationLifecycleError(ValueError):
    """Stable lifecycle error code without identifiers or storage details."""


METRIC_CATALOG: tuple[BetaMetricDefinition, ...] = (
    BetaMetricDefinition(name="activated_teacher", unit="count", description="窗口内至少完成一次核心任务的去重教师数。", numerator="完成核心任务的去重教师", denominator="无"),
    BetaMetricDefinition(name="weekly_verified_teacher_tasks", unit="count", description="窗口结束前七天内完成且属于 verified_source 或 program_verified 的去重任务数。", numerator="近七天可信完成任务", denominator="无"),
    BetaMetricDefinition(name="task_acceptance_rate", unit="rate", description="窗口内每个任务最后一次明确接受/拒绝决定中的接受比例。", numerator="最后决定为接受的任务", denominator="存在明确接受或拒绝决定的任务"),
    BetaMetricDefinition(name="search_to_selection_rate", unit="rate", description="已完成搜索中产生明确结果选择的比例。", numerator="选择了结果的搜索任务", denominator="已完成搜索任务"),
    BetaMetricDefinition(name="paper_generation_to_export_rate", unit="rate", description="已生成试卷中完成导出的比例。", numerator="已导出试卷任务", denominator="已生成试卷任务"),
    BetaMetricDefinition(name="lesson_generation_to_save_rate", unit="rate", description="已生成教案中明确保存的比例。", numerator="已保存教案任务", denominator="已生成教案任务"),
    BetaMetricDefinition(name="private_library_activation_rate", unit="rate", description="窗口内活跃教师中至少确认一次私有资料导入的比例。", numerator="确认私有资料导入的教师", denominator="窗口内产生任一验证事件的教师"),
    BetaMetricDefinition(name="private_question_authoring_acceptance_rate", unit="rate", description="已完成辅助命题中明确保存到本人私题库的比例。", numerator="已保存辅助命题任务", denominator="已完成辅助命题任务"),
    BetaMetricDefinition(name="week_1_retention", unit="rate", description="首次完成任务后第 7 至 13 天再次完成任务的教师比例。", numerator="第 1 周回访教师", denominator="截至窗口结束已具备 14 天观察期的激活教师"),
    BetaMetricDefinition(name="week_4_retention", unit="rate", description="首次完成任务后第 28 至 34 天再次完成任务的教师比例。", numerator="第 4 周回访教师", denominator="截至窗口结束已具备 35 天观察期的激活教师"),
    BetaMetricDefinition(name="verified_math_error_rate", unit="rate", description="verified_source/program_verified 完成任务中，经教师确认的严重数学错误比例。", numerator="可信任务的确认严重数学错误", denominator="可信等级为 verified_source 或 program_verified 的完成任务"),
    BetaMetricDefinition(name="agent_tool_failure_rate", unit="rate", description="Agent Tool 明确结束事件中的失败比例。", numerator="Agent Tool 失败事件", denominator="Agent Tool 成功与失败事件"),
    BetaMetricDefinition(name="average_model_cost_per_teacher", unit="usd", description="窗口内模型成本除以产生验证事件的去重教师数。", numerator="模型成本美元总额", denominator="窗口内产生验证事件的教师"),
    BetaMetricDefinition(name="average_model_cost_per_completed_task", unit="usd", description="窗口内模型成本除以完成任务数。", numerator="模型成本美元总额", denominator="完成的去重任务"),
    BetaMetricDefinition(name="p50_latency", unit="milliseconds", description="窗口内完成任务耗时的第 50 百分位。", numerator="任务完成耗时样本", denominator="完成任务数"),
    BetaMetricDefinition(name="p95_latency", unit="milliseconds", description="窗口内完成任务耗时的第 95 百分位。", numerator="任务完成耗时样本", denominator="完成任务数"),
)


class BetaValidationMetrics:
    """Persist pseudonymous facts and calculate the versioned M13 metric contract.

    The Interface is intentionally content blind. It owns notice acknowledgment,
    strict event recording, aggregate snapshots, participant export and deletion.
    Raw owner and task identifiers are HMAC-digested before SQLite sees them.
    """

    def __init__(
        self,
        *,
        database_path: Path,
        identity_secret: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(identity_secret) < 32:
            raise ValueError("M13 指标身份摘要密钥至少需要 32 个字符。")
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._secret = identity_secret.encode("utf-8")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._initialize()

    def record(
        self,
        *,
        owner_id: str,
        observation: BetaValidationObservation,
    ) -> BetaValidationReceipt:
        return self._record_batch(
            owner_id=owner_id,
            observations=(observation,),
        )[0]

    def _record_batch(
        self,
        *,
        owner_id: str,
        observations: tuple[BetaValidationObservation, ...],
    ) -> tuple[BetaValidationReceipt, ...]:
        """Atomically persist one server fact and its derived completion event."""

        if not observations:
            return ()
        occurred_at = self._now()
        participant_key = self._participant_key(owner_id)
        prepared = tuple(
            (
                f"bve_{uuid.uuid4().hex}",
                observation,
                self._digest("task", f"{owner_id}\x00{observation.task_ref}"),
            )
            for observation in observations
        )
        with self._connect() as connection:
            # Serialize the consent check with participant deletion. Either the
            # event commits before an exit transaction (and is deleted by it),
            # or it observes no current acknowledgment and is rejected.
            connection.execute("BEGIN IMMEDIATE")
            acknowledged = connection.execute(
                """SELECT 1 FROM m13_beta_validation_participants
                   WHERE participant_key = ? AND notice_version = ?""",
                (participant_key, NOTICE_VERSION),
            ).fetchone()
            if acknowledged is None:
                raise BetaValidationLifecycleError(
                    "BETA_VALIDATION_NOTICE_ACKNOWLEDGMENT_REQUIRED"
                )
            connection.executemany(
                """INSERT INTO m13_beta_validation_events
                   (event_id, definition_version, participant_key, task_key,
                    workflow, event_type, trust_tier, duration_ms,
                    model_cost_usd, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(
                    (
                        event_id,
                        METRIC_DEFINITION_VERSION,
                        participant_key,
                        task_key,
                        observation.workflow,
                        observation.event_type,
                        observation.trust_tier,
                        observation.duration_ms,
                        str(observation.model_cost_usd),
                        occurred_at.isoformat(),
                    )
                    for event_id, observation, task_key in prepared
                ),
            )
        return tuple(
            BetaValidationReceipt(event_id=event_id, occurred_at=occurred_at)
            for event_id, _, _ in prepared
        )

    def acknowledge(self, *, owner_id: str) -> BetaValidationParticipation:
        participant_key = self._participant_key(owner_id)
        acknowledged_at = self._now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO m13_beta_validation_participants
                       (participant_key, notice_version, acknowledged_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(participant_key) DO UPDATE SET
                       notice_version = excluded.notice_version,
                       acknowledged_at = excluded.acknowledged_at
                   WHERE m13_beta_validation_participants.notice_version
                         != excluded.notice_version""",
                (participant_key, NOTICE_VERSION, acknowledged_at.isoformat()),
            )
            stored = connection.execute(
                """SELECT acknowledged_at FROM m13_beta_validation_participants
                   WHERE participant_key = ? AND notice_version = ?""",
                (participant_key, NOTICE_VERSION),
            ).fetchone()
        return BetaValidationParticipation(
            acknowledged_at=datetime.fromisoformat(stored["acknowledged_at"]).astimezone(
                timezone.utc
            )
        )

    def export_participant(self, *, owner_id: str) -> BetaParticipantMetricExport:
        participant_key = self._participant_key(owner_id)
        window_end = self._now()
        window_start = window_end - timedelta(days=RETENTION_DAYS)
        with self._connect() as connection:
            participation = connection.execute(
                """SELECT acknowledged_at FROM m13_beta_validation_participants
                   WHERE participant_key = ? AND notice_version = ?""",
                (participant_key, NOTICE_VERSION),
            ).fetchone()
        retained_rows = self._rows_before(
            window_end + timedelta(microseconds=1),
            participant_key=participant_key,
        )
        window_rows = [
            row for row in retained_rows if window_start <= self._row_time(row)
        ]
        return BetaParticipantMetricExport(
            generated_at=window_end,
            window_start=window_start,
            window_end=window_end,
            acknowledged_at=(
                datetime.fromisoformat(participation["acknowledged_at"]).astimezone(
                    timezone.utc
                )
                if participation is not None
                else None
            ),
            event_count=len(window_rows),
            metrics=self._aggregate(
                window_rows=window_rows,
                all_rows=window_rows,
                window_end=window_end,
            ),
            trust_tier_error_rates=self._trust_tier_error_rates(window_rows),
        )

    def delete_participant(
        self,
        *,
        owner_id: str,
        confirmed: bool = False,
    ) -> BetaParticipantDeletion:
        if confirmed is not True:
            raise BetaValidationLifecycleError(
                "BETA_VALIDATION_DELETE_CONFIRMATION_REQUIRED"
            )
        participant_key = self._participant_key(owner_id)
        deleted_at = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            deleted_events = connection.execute(
                "DELETE FROM m13_beta_validation_events WHERE participant_key = ?",
                (participant_key,),
            ).rowcount
            participation_removed = (
                connection.execute(
                    """DELETE FROM m13_beta_validation_participants
                       WHERE participant_key = ?""",
                    (participant_key,),
                ).rowcount
                > 0
            )
        return BetaParticipantDeletion(
            deleted_at=deleted_at,
            deleted_events=deleted_events,
            participation_removed=participation_removed,
        )

    def snapshot(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> BetaMetricSnapshot:
        start = self._utc(window_start)
        end = self._utc(window_end)
        if start >= end:
            raise ValueError("指标窗口结束时间必须晚于开始时间。")
        rows = self._rows_before(end)
        window_rows = [row for row in rows if start <= self._row_time(row) < end]
        metrics = self._aggregate(window_rows=window_rows, all_rows=rows, window_end=end)
        return BetaMetricSnapshot(
            window_start=start,
            window_end=end,
            generated_at=self._now(),
            metrics=metrics,
            trust_tier_error_rates=self._trust_tier_error_rates(window_rows),
        )

    def _aggregate(self, *, window_rows: list[sqlite3.Row], all_rows: list[sqlite3.Row], window_end: datetime) -> dict[str, BetaMetricValue]:
        completed = self._task_set(window_rows, "task_completed")
        active_participants = {row["participant_key"] for row in window_rows}
        activated = {participant for participant, _ in completed}
        trailing_week = window_end - timedelta(days=7)
        weekly_verified = {
            (row["participant_key"], row["task_key"])
            for row in window_rows
            if row["event_type"] == "task_completed"
            and row["trust_tier"] in {"verified_source", "program_verified"}
            and self._row_time(row) >= trailing_week
        }
        decisions: dict[tuple[str, str], sqlite3.Row] = {}
        for row in window_rows:
            if row["event_type"] not in {"task_accepted", "task_rejected"}:
                continue
            key = (row["participant_key"], row["task_key"])
            # Rows are ordered by timestamp and SQLite insertion sequence, so a
            # same-clock correction deterministically replaces the prior choice.
            decisions[key] = row
        accepted = sum(row["event_type"] == "task_accepted" for row in decisions.values())
        verified_completed = {
            (row["participant_key"], row["task_key"])
            for row in window_rows
            if row["event_type"] == "task_completed"
            and row["trust_tier"] in {"verified_source", "program_verified"}
        }
        verified_errors = {
            (row["participant_key"], row["task_key"])
            for row in window_rows
            if row["event_type"] == "serious_math_error_confirmed"
            and row["trust_tier"] in {"verified_source", "program_verified"}
        } & verified_completed
        tool_success = sum(row["event_type"] == "agent_tool_succeeded" for row in window_rows)
        tool_failed = sum(row["event_type"] == "agent_tool_failed" for row in window_rows)
        total_cost = sum((Decimal(row["model_cost_usd"]) for row in window_rows), Decimal("0"))
        durations = sorted(
            int(row["duration_ms"])
            for row in window_rows
            if row["event_type"] == "task_completed" and row["duration_ms"] is not None
        )
        week_1 = self._retention(all_rows, window_end=window_end, start_day=7, eligible_day=14)
        week_4 = self._retention(all_rows, window_end=window_end, start_day=28, eligible_day=35)
        return {
            "activated_teacher": self._count(len(activated)),
            "weekly_verified_teacher_tasks": self._count(len(weekly_verified)),
            "task_acceptance_rate": self._rate(accepted, len(decisions)),
            "search_to_selection_rate": self._conversion(window_rows, "search_completed", "search_result_selected"),
            "paper_generation_to_export_rate": self._conversion(window_rows, "paper_generated", "paper_exported"),
            "lesson_generation_to_save_rate": self._conversion(window_rows, "lesson_generated", "lesson_saved"),
            "private_library_activation_rate": self._participant_rate(window_rows, "private_library_import_confirmed", active_participants),
            "private_question_authoring_acceptance_rate": self._conversion(window_rows, "authoring_completed", "authoring_saved"),
            "week_1_retention": self._rate(*week_1),
            "week_4_retention": self._rate(*week_4),
            "verified_math_error_rate": self._rate(len(verified_errors), len(verified_completed)),
            "agent_tool_failure_rate": self._rate(tool_failed, tool_success + tool_failed),
            "average_model_cost_per_teacher": self._average(total_cost, len(active_participants), "usd"),
            "average_model_cost_per_completed_task": self._average(total_cost, len(completed), "usd"),
            "p50_latency": self._percentile(durations, 0.50),
            "p95_latency": self._percentile(durations, 0.95),
        }

    def _trust_tier_error_rates(self, rows: list[sqlite3.Row]) -> dict[BetaTrustTier, BetaMetricValue]:
        result: dict[BetaTrustTier, BetaMetricValue] = {}
        for tier in _TRUST_TIERS:
            completed = {
                (row["participant_key"], row["task_key"])
                for row in rows
                if row["event_type"] == "task_completed" and row["trust_tier"] == tier
            }
            errors = {
                (row["participant_key"], row["task_key"])
                for row in rows
                if row["event_type"] == "serious_math_error_confirmed" and row["trust_tier"] == tier
            } & completed
            result[tier] = self._rate(len(errors), len(completed))
        return result

    def _retention(self, rows: list[sqlite3.Row], *, window_end: datetime, start_day: int, eligible_day: int) -> tuple[int, int]:
        completions: dict[str, list[datetime]] = {}
        for row in rows:
            if row["event_type"] == "task_completed":
                completions.setdefault(row["participant_key"], []).append(self._row_time(row))
        retained = 0
        eligible = 0
        for times in completions.values():
            ordered = sorted(times)
            activated_at = ordered[0]
            if activated_at + timedelta(days=eligible_day) > window_end:
                continue
            eligible += 1
            period_start = activated_at + timedelta(days=start_day)
            period_end = activated_at + timedelta(days=eligible_day)
            retained += any(period_start <= item < period_end for item in ordered)
        return retained, eligible

    @classmethod
    def _conversion(cls, rows: list[sqlite3.Row], denominator_type: str, numerator_type: str) -> BetaMetricValue:
        denominator = cls._task_set(rows, denominator_type)
        numerator = cls._task_set(rows, numerator_type) & denominator
        return cls._rate(len(numerator), len(denominator))

    @staticmethod
    def _participant_rate(rows: list[sqlite3.Row], event_type: str, denominator: set[str]) -> BetaMetricValue:
        numerator = {row["participant_key"] for row in rows if row["event_type"] == event_type} & denominator
        return BetaValidationMetrics._rate(len(numerator), len(denominator))

    @staticmethod
    def _task_set(rows: Iterable[sqlite3.Row], event_type: str) -> set[tuple[str, str]]:
        return {
            (row["participant_key"], row["task_key"])
            for row in rows
            if row["event_type"] == event_type
        }

    @staticmethod
    def _count(value: int) -> BetaMetricValue:
        return BetaMetricValue(value=float(value), numerator=float(value), unit="count")

    @staticmethod
    def _rate(numerator: int, denominator: int) -> BetaMetricValue:
        value = numerator / denominator if denominator else None
        return BetaMetricValue(value=value, numerator=float(numerator), denominator=float(denominator), unit="rate")

    @staticmethod
    def _average(numerator: Decimal, denominator: int, unit: str) -> BetaMetricValue:
        value = float(numerator / denominator) if denominator else None
        return BetaMetricValue(value=value, numerator=float(numerator), denominator=float(denominator), unit=unit)

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> BetaMetricValue:
        if not values:
            return BetaMetricValue(value=None, numerator=0, denominator=0, unit="milliseconds")
        rank = max(0, math.ceil(percentile * len(values)) - 1)
        return BetaMetricValue(value=float(values[rank]), numerator=float(values[rank]), denominator=float(len(values)), unit="milliseconds")

    def _digest(self, namespace: str, value: str) -> str:
        return hmac.new(self._secret, f"{namespace}\x00{value}".encode("utf-8"), hashlib.sha256).hexdigest()

    def _rows_before(
        self,
        end: datetime,
        *,
        participant_key: str | None = None,
    ) -> list[sqlite3.Row]:
        participant_filter = " AND participant_key = ?" if participant_key else ""
        parameters = (
            (METRIC_DEFINITION_VERSION, end.isoformat(), participant_key)
            if participant_key
            else (METRIC_DEFINITION_VERSION, end.isoformat())
        )
        with self._connect() as connection:
            return connection.execute(
                f"""SELECT rowid AS sequence, participant_key, task_key,
                          workflow, event_type,
                          trust_tier, duration_ms, model_cost_usd, occurred_at
                   FROM m13_beta_validation_events
                   WHERE definition_version = ? AND occurred_at < ?
                   {participant_filter}
                   ORDER BY occurred_at, sequence""",
                parameters,
            ).fetchall()

    def _participant_key(self, owner_id: str) -> str:
        if not _OWNER_PATTERN.fullmatch(owner_id):
            raise ValueError("owner_id 必须是服务端生成的非内容标识。")
        return self._digest("participant", owner_id)

    @staticmethod
    def _row_time(row: sqlite3.Row) -> datetime:
        return datetime.fromisoformat(row["occurred_at"]).astimezone(timezone.utc)

    def _now(self) -> datetime:
        return self._utc(self._clock())

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("M13 指标时间必须包含时区。")
        return value.astimezone(timezone.utc)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS m13_beta_validation_events (
                    event_id TEXT PRIMARY KEY,
                    definition_version TEXT NOT NULL,
                    participant_key TEXT NOT NULL,
                    task_key TEXT NOT NULL,
                    workflow TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    trust_tier TEXT,
                    duration_ms INTEGER,
                    model_cost_usd TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_m13_validation_window
                    ON m13_beta_validation_events (definition_version, occurred_at);
                CREATE INDEX IF NOT EXISTS idx_m13_validation_participant
                    ON m13_beta_validation_events (participant_key, occurred_at);
                CREATE TABLE IF NOT EXISTS m13_beta_validation_participants (
                    participant_key TEXT PRIMARY KEY,
                    notice_version TEXT NOT NULL,
                    acknowledged_at TEXT NOT NULL
                );
                """
            )
