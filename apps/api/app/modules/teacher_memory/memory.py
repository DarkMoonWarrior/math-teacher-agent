from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.modules.teacher_memory.schemas import (
    TeacherMemoryCommand,
    TeacherMemoryProfile,
    TeacherPlanningDefaults,
    TeacherPlanningPreference,
    TeacherPreference,
    TeacherPreferenceProposal,
    TeacherPreferenceProposalEvidence,
    TeacherPreferenceFeedback,
    TeacherPreferenceSignal,
    TeacherPreferenceKey,
    TeacherPreferenceSource,
    TeacherPreferenceValue,
)


PREFERENCE_LABELS: dict[str, str] = {
    "default_grade": "默认年级",
    "default_difficulty": "默认难度",
    "default_lesson_minutes": "默认课时",
    "solution_detail_level": "解析详略",
    "preferred_question_types": "常用题型",
}
GRADES = {"高一", "高二", "高三", "高中通用"}
DETAIL_LEVELS = {"concise", "standard", "detailed"}
QUESTION_TYPES = {"single_choice", "multiple_choice", "fill_blank", "open_response"}
EVIDENCE_LABELS = {
    "confirmed_lesson_version": "已确认并保存的教案版本",
    "confirmed_paper_version": "已确认并保存的试卷版本",
}
SIGNAL_KEYS = {
    "confirmed_lesson_version": {"default_grade", "default_lesson_minutes"},
    "confirmed_paper_version": {"default_grade", "default_difficulty"},
}
PROPOSAL_THRESHOLD = 3


class TeacherMemoryError(ValueError):
    pass


class TeacherMemoryConflict(TeacherMemoryError):
    pass


class TeacherMemory:
    """Owner-scoped structured preference memory.

    Callers provide identity and commands; persistence, provenance and validation
    remain private to this module.
    """

    def __init__(self, *, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def profile(self, *, owner_id: str) -> TeacherMemoryProfile:
        with self._connect() as connection:
            return self._profile(connection, owner_id=owner_id)

    def planning_defaults(self, *, owner_id: str) -> TeacherPlanningDefaults:
        """Return only preferences that are safe to use as editable planning defaults."""

        profile = self.profile(owner_id=owner_id)
        allowed = {"default_grade", "default_difficulty", "default_lesson_minutes"}
        return TeacherPlanningDefaults(
            preferences=[
                TeacherPlanningPreference(
                    key=item.key,
                    label=item.label,
                    value=item.value,
                    source=item.source,
                )
                for item in profile.preferences
                if item.key in allowed
            ]
        )

    def apply(
        self,
        command: TeacherMemoryCommand | TeacherPreferenceSignal,
        *,
        owner_id: str,
    ) -> TeacherMemoryProfile:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._profile(connection, owner_id=owner_id)
            if isinstance(command, TeacherPreferenceSignal):
                return self._observe(
                    connection,
                    command=command,
                    current=current,
                    owner_id=owner_id,
                )
            if command.expected_version is not None and command.expected_version != current.version:
                raise TeacherMemoryConflict("教师偏好已在其他页面更新，请刷新后重试。")

            if command.operation == "delete_all":
                return self._delete_all(
                    connection,
                    command=command,
                    current=current,
                    owner_id=owner_id,
                )

            if command.operation in {"accept_proposal", "reject_proposal", "correct_proposal"}:
                return self._review_proposal(
                    connection,
                    command=command,
                    current=current,
                    owner_id=owner_id,
                )

            changed = False
            now = datetime.now(timezone.utc).isoformat()
            if command.operation == "upsert":
                if command.key is None or command.value is None:
                    raise TeacherMemoryError("保存偏好时必须提供偏好项和值。")
                value = self._validate_value(command.key, command.value)
                connection.execute(
                    """INSERT INTO m11_teacher_preferences
                       (owner_id, preference_key, value_json, source_kind, confidence, updated_at)
                       VALUES (?, ?, ?, 'teacher_explicit', 1.0, ?)
                       ON CONFLICT(owner_id, preference_key) DO UPDATE SET
                         value_json = excluded.value_json,
                         source_kind = 'teacher_explicit',
                         confidence = 1.0,
                         updated_at = excluded.updated_at""",
                    (owner_id, command.key, json.dumps(value, ensure_ascii=False), now),
                )
                connection.execute(
                    "DELETE FROM m11_teacher_memory_proposals WHERE owner_id = ? AND preference_key = ?",
                    (owner_id, command.key),
                )
                connection.execute(
                    "DELETE FROM m11_teacher_memory_observations WHERE owner_id = ? AND preference_key = ?",
                    (owner_id, command.key),
                )
                connection.execute(
                    """UPDATE m11_teacher_memory_feedback
                       SET active_suppression = 0
                       WHERE owner_id = ? AND preference_key = ? AND active_suppression = 1""",
                    (owner_id, command.key),
                )
                changed = True
            elif command.operation == "remove":
                if command.key is None:
                    raise TeacherMemoryError("删除偏好时必须提供偏好项。")
                changed = connection.execute(
                    "DELETE FROM m11_teacher_preferences WHERE owner_id = ? AND preference_key = ?",
                    (owner_id, command.key),
                ).rowcount > 0
            elif command.operation == "set_auto_learning":
                if command.enabled is None:
                    raise TeacherMemoryError("设置自动学习时必须提供开关状态。")
                changed = command.enabled != current.auto_learning_enabled
            else:
                raise TeacherMemoryError("不支持的教师偏好操作。")

            if changed:
                next_version = current.version + 1
                auto_learning = (
                    command.enabled
                    if command.operation == "set_auto_learning"
                    else current.auto_learning_enabled
                )
                connection.execute(
                    """INSERT INTO m11_teacher_memory_profiles
                       (owner_id, version, auto_learning_enabled, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(owner_id) DO UPDATE SET
                         version = excluded.version,
                         auto_learning_enabled = excluded.auto_learning_enabled,
                         updated_at = excluded.updated_at""",
                    (owner_id, next_version, int(bool(auto_learning)), now, now),
                )
            return self._profile(connection, owner_id=owner_id)

    def _delete_all(
        self,
        connection: sqlite3.Connection,
        *,
        command: TeacherMemoryCommand,
        current: TeacherMemoryProfile,
        owner_id: str,
    ) -> TeacherMemoryProfile:
        if command.confirmation != "删除全部教师记忆":
            raise TeacherMemoryError("请输入“删除全部教师记忆”以确认永久删除。")
        now = datetime.now(timezone.utc).isoformat()
        for table in (
            "m11_teacher_preferences",
            "m11_teacher_memory_proposals",
            "m11_teacher_memory_observations",
            "m11_teacher_memory_feedback",
        ):
            connection.execute(f"DELETE FROM {table} WHERE owner_id = ?", (owner_id,))
        self._write_profile_state(
            connection,
            owner_id=owner_id,
            version=current.version + 1,
            auto_learning_enabled=False,
            now=now,
        )
        return self._profile(connection, owner_id=owner_id)

    def _review_proposal(
        self,
        connection: sqlite3.Connection,
        *,
        command: TeacherMemoryCommand,
        current: TeacherMemoryProfile,
        owner_id: str,
    ) -> TeacherMemoryProfile:
        if command.proposal_id is None:
            raise TeacherMemoryError("处理偏好提议时必须提供提议编号。")
        row = connection.execute(
            """SELECT proposal_id, preference_key, value_json, evidence_category,
                      occurrence_count, confidence
               FROM m11_teacher_memory_proposals
               WHERE owner_id = ? AND proposal_id = ?""",
            (owner_id, command.proposal_id),
        ).fetchone()
        if row is None:
            raise TeacherMemoryError("偏好提议不存在或已被处理，请刷新后重试。")

        key = row["preference_key"]
        proposed_value = json.loads(row["value_json"])
        resolved_value: TeacherPreferenceValue | None = None
        action = command.operation.removesuffix("_proposal")
        if command.operation == "accept_proposal":
            resolved_value = self._validate_value(key, proposed_value)
        elif command.operation == "correct_proposal":
            if command.value is None:
                raise TeacherMemoryError("修正偏好提议时必须提供修正后的值。")
            resolved_value = self._validate_value(key, command.value)

        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """UPDATE m11_teacher_memory_feedback
               SET active_suppression = 0
               WHERE owner_id = ? AND preference_key = ? AND active_suppression = 1""",
            (owner_id, key),
        )
        next_eligible_occurrence_count = (
            int(row["occurrence_count"]) + PROPOSAL_THRESHOLD
            if command.operation == "reject_proposal"
            else None
        )
        connection.execute(
            """INSERT INTO m11_teacher_memory_feedback
               (owner_id, proposal_id, preference_key, proposed_value_json,
                resolved_value_json, evidence_category, occurrence_count, confidence,
                action, active_suppression, next_eligible_occurrence_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                owner_id,
                row["proposal_id"],
                key,
                row["value_json"],
                json.dumps(resolved_value, ensure_ascii=False, sort_keys=True)
                if resolved_value is not None
                else None,
                row["evidence_category"],
                int(row["occurrence_count"]),
                float(row["confidence"]),
                action,
                int(command.operation == "reject_proposal"),
                next_eligible_occurrence_count,
                now,
            ),
        )

        if resolved_value is not None:
            connection.execute(
                """INSERT INTO m11_teacher_preferences
                   (owner_id, preference_key, value_json, source_kind, confidence, updated_at)
                   VALUES (?, ?, ?, 'teacher_explicit', 1.0, ?)
                   ON CONFLICT(owner_id, preference_key) DO UPDATE SET
                     value_json = excluded.value_json,
                     source_kind = 'teacher_explicit',
                     confidence = 1.0,
                     updated_at = excluded.updated_at""",
                (
                    owner_id,
                    key,
                    json.dumps(resolved_value, ensure_ascii=False),
                    now,
                ),
            )
            connection.execute(
                "DELETE FROM m11_teacher_memory_proposals WHERE owner_id = ? AND preference_key = ?",
                (owner_id, key),
            )
            connection.execute(
                "DELETE FROM m11_teacher_memory_observations WHERE owner_id = ? AND preference_key = ?",
                (owner_id, key),
            )
        else:
            connection.execute(
                "DELETE FROM m11_teacher_memory_proposals WHERE owner_id = ? AND proposal_id = ?",
                (owner_id, command.proposal_id),
            )

        self._write_profile_state(
            connection,
            owner_id=owner_id,
            version=current.version + 1,
            auto_learning_enabled=current.auto_learning_enabled,
            now=now,
        )
        return self._profile(connection, owner_id=owner_id)

    def _observe(
        self,
        connection: sqlite3.Connection,
        *,
        command: TeacherPreferenceSignal,
        current: TeacherMemoryProfile,
        owner_id: str,
    ) -> TeacherMemoryProfile:
        if not current.auto_learning_enabled:
            return current
        allowed_keys = SIGNAL_KEYS[command.evidence_category]
        if command.key not in allowed_keys:
            raise TeacherMemoryError("该证据类别不能推断这项教师偏好。")
        value = self._validate_value(command.key, command.value)
        if any(item.key == command.key for item in current.preferences):
            return current

        now = datetime.now(timezone.utc).isoformat()
        value_json = json.dumps(value, ensure_ascii=False, sort_keys=True)
        inserted = connection.execute(
            """INSERT OR IGNORE INTO m11_teacher_memory_observations
               (owner_id, evidence_id, preference_key, value_json, evidence_category, observed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                owner_id,
                command.evidence_id,
                command.key,
                value_json,
                command.evidence_category,
                now,
            ),
        ).rowcount > 0
        if not inserted:
            return current

        row = connection.execute(
            """SELECT COUNT(*) AS occurrence_count
               FROM m11_teacher_memory_observations
               WHERE owner_id = ? AND preference_key = ? AND value_json = ?
                 AND evidence_category = ?""",
            (owner_id, command.key, value_json, command.evidence_category),
        ).fetchone()
        occurrence_count = int(row["occurrence_count"])
        if occurrence_count < PROPOSAL_THRESHOLD:
            return current

        suppression = connection.execute(
            """SELECT feedback_id, next_eligible_occurrence_count
               FROM m11_teacher_memory_feedback
               WHERE owner_id = ? AND preference_key = ? AND proposed_value_json = ?
                 AND evidence_category = ? AND active_suppression = 1
               ORDER BY feedback_id DESC LIMIT 1""",
            (owner_id, command.key, value_json, command.evidence_category),
        ).fetchone()
        if suppression is not None:
            if occurrence_count < int(suppression["next_eligible_occurrence_count"]):
                return current
            connection.execute(
                """UPDATE m11_teacher_memory_feedback
                   SET active_suppression = 0 WHERE feedback_id = ?""",
                (suppression["feedback_id"],),
            )

        proposal_id = "proposal_" + hashlib.sha256(
            f"{command.key}\0{value_json}\0{command.evidence_category}".encode("utf-8")
        ).hexdigest()[:20]
        confidence = min(0.95, 0.55 + occurrence_count * 0.08)
        existing = connection.execute(
            """SELECT created_at FROM m11_teacher_memory_proposals
               WHERE owner_id = ? AND proposal_id = ?""",
            (owner_id, proposal_id),
        ).fetchone()
        connection.execute(
            """INSERT INTO m11_teacher_memory_proposals
               (owner_id, proposal_id, preference_key, value_json, evidence_category,
                occurrence_count, confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(owner_id, proposal_id) DO UPDATE SET
                 occurrence_count = excluded.occurrence_count,
                 confidence = excluded.confidence,
                 updated_at = excluded.updated_at""",
            (
                owner_id,
                proposal_id,
                command.key,
                value_json,
                command.evidence_category,
                occurrence_count,
                confidence,
                existing["created_at"] if existing else now,
                now,
            ),
        )
        self._write_profile_state(
            connection,
            owner_id=owner_id,
            version=current.version + 1,
            auto_learning_enabled=current.auto_learning_enabled,
            now=now,
        )
        return self._profile(connection, owner_id=owner_id)

    @staticmethod
    def _write_profile_state(
        connection: sqlite3.Connection,
        *,
        owner_id: str,
        version: int,
        auto_learning_enabled: bool,
        now: str,
    ) -> None:
        connection.execute(
            """INSERT INTO m11_teacher_memory_profiles
               (owner_id, version, auto_learning_enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(owner_id) DO UPDATE SET
                 version = excluded.version,
                 auto_learning_enabled = excluded.auto_learning_enabled,
                 updated_at = excluded.updated_at""",
            (owner_id, version, int(auto_learning_enabled), now, now),
        )

    def _validate_value(
        self,
        key: TeacherPreferenceKey,
        value: TeacherPreferenceValue,
    ) -> TeacherPreferenceValue:
        if key == "default_grade":
            if not isinstance(value, str) or value not in GRADES:
                raise TeacherMemoryError("默认年级必须是高一、高二、高三或高中通用。")
            return value
        if key == "default_difficulty":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
                raise TeacherMemoryError("默认难度必须是 1 至 5 的整数。")
            return value
        if key == "default_lesson_minutes":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 300:
                raise TeacherMemoryError("默认课时必须是 1 至 300 分钟。")
            return value
        if key == "solution_detail_level":
            if not isinstance(value, str) or value not in DETAIL_LEVELS:
                raise TeacherMemoryError("解析详略必须是简洁、标准或详细。")
            return value
        if key == "preferred_question_types":
            if (
                not isinstance(value, list)
                or not value
                or len(value) > len(QUESTION_TYPES)
                or any(not isinstance(item, str) or item not in QUESTION_TYPES for item in value)
            ):
                raise TeacherMemoryError("常用题型必须从受支持题型中选择。")
            return list(dict.fromkeys(value))
        raise TeacherMemoryError("不支持的教师偏好项。")

    def _profile(self, connection: sqlite3.Connection, *, owner_id: str) -> TeacherMemoryProfile:
        profile_row = connection.execute(
            "SELECT version, auto_learning_enabled FROM m11_teacher_memory_profiles WHERE owner_id = ?",
            (owner_id,),
        ).fetchone()
        rows = connection.execute(
            """SELECT preference_key, value_json, source_kind, confidence, updated_at
               FROM m11_teacher_preferences
               WHERE owner_id = ? ORDER BY preference_key""",
            (owner_id,),
        ).fetchall()
        preferences = [
            TeacherPreference(
                key=row["preference_key"],
                label=PREFERENCE_LABELS[row["preference_key"]],
                value=json.loads(row["value_json"]),
                source=TeacherPreferenceSource(
                    kind=row["source_kind"],
                    confidence=float(row["confidence"]),
                ),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
        proposal_rows = connection.execute(
            """SELECT proposal_id, preference_key, value_json, evidence_category,
                      occurrence_count, confidence, created_at, updated_at
               FROM m11_teacher_memory_proposals
               WHERE owner_id = ? ORDER BY updated_at DESC""",
            (owner_id,),
        ).fetchall()
        proposals = [
            TeacherPreferenceProposal(
                proposal_id=row["proposal_id"],
                key=row["preference_key"],
                label=PREFERENCE_LABELS[row["preference_key"]],
                value=json.loads(row["value_json"]),
                confidence=float(row["confidence"]),
                evidence=TeacherPreferenceProposalEvidence(
                    category=row["evidence_category"],
                    label=EVIDENCE_LABELS[row["evidence_category"]],
                    occurrence_count=int(row["occurrence_count"]),
                ),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in proposal_rows
        ]
        feedback_rows = connection.execute(
            """SELECT feedback_id, proposal_id, preference_key, proposed_value_json,
                      resolved_value_json, evidence_category, occurrence_count,
                      confidence, action, created_at
               FROM m11_teacher_memory_feedback
               WHERE owner_id = ? ORDER BY feedback_id DESC""",
            (owner_id,),
        ).fetchall()
        feedback = [
            TeacherPreferenceFeedback(
                feedback_id=f"feedback_{row['feedback_id']}",
                proposal_id=row["proposal_id"],
                key=row["preference_key"],
                label=PREFERENCE_LABELS[row["preference_key"]],
                proposed_value=json.loads(row["proposed_value_json"]),
                resolved_value=(
                    json.loads(row["resolved_value_json"])
                    if row["resolved_value_json"] is not None
                    else None
                ),
                action=row["action"],
                confidence=float(row["confidence"]),
                evidence=TeacherPreferenceProposalEvidence(
                    category=row["evidence_category"],
                    label=EVIDENCE_LABELS[row["evidence_category"]],
                    occurrence_count=int(row["occurrence_count"]),
                ),
                created_at=row["created_at"],
            )
            for row in feedback_rows
        ]
        return TeacherMemoryProfile(
            version=int(profile_row["version"]) if profile_row else 0,
            auto_learning_enabled=bool(profile_row["auto_learning_enabled"]) if profile_row else False,
            preferences=preferences,
            proposals=proposals,
            feedback=feedback,
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS m11_teacher_memory_profiles (
                    owner_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    auto_learning_enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS m11_teacher_preferences (
                    owner_id TEXT NOT NULL,
                    preference_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (owner_id, preference_key)
                );
                CREATE TABLE IF NOT EXISTS m11_teacher_memory_observations (
                    owner_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    preference_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    evidence_category TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY (owner_id, evidence_id, preference_key)
                );
                CREATE INDEX IF NOT EXISTS idx_m11_teacher_memory_observations_lookup
                    ON m11_teacher_memory_observations
                    (owner_id, preference_key, value_json, evidence_category);
                CREATE TABLE IF NOT EXISTS m11_teacher_memory_proposals (
                    owner_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    preference_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    evidence_category TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (owner_id, proposal_id)
                );
                CREATE TABLE IF NOT EXISTS m11_teacher_memory_feedback (
                    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    preference_key TEXT NOT NULL,
                    proposed_value_json TEXT NOT NULL,
                    resolved_value_json TEXT,
                    evidence_category TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    action TEXT NOT NULL,
                    active_suppression INTEGER NOT NULL DEFAULT 0,
                    next_eligible_occurrence_count INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_m11_teacher_memory_feedback_suppression
                    ON m11_teacher_memory_feedback
                    (owner_id, preference_key, proposed_value_json, evidence_category,
                     active_suppression);
                """
            )
