from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
from typing import Iterator, Protocol

from app.core.deletion import is_link_or_reparse
from app.modules.account_identity import VersionedHmacKeyRing
from app.modules.private_object_storage import (
    PRIVATE_OBJECT_BINDING_SCHEMA_VERSION,
    PrivateObjectBinding,
    PrivateObjectConflict,
    PrivateObjectDomain,
    PrivateObjectNamespace,
    PrivateObjectNotFound,
    PrivateObjectRetention,
    PrivateObjectScope,
)

from .contracts import (
    PERSISTENT_TASK_SCHEMA_VERSION,
    PersistentTaskConflict,
    PersistentTaskPayloadError,
    PersistentTaskUnavailable,
    PersistentTaskView,
)


_TASK_ID = re.compile(r"^task_[0-9a-f]{32}$")
_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_PAYLOAD_BYTES = 8 * 1024 * 1024
_ACTIVE = frozenset({"queued", "running"})
_SCHEMA_TABLES = frozenset({"persistent_task_meta", "persistent_tasks"})


class _PrivateObjectStore(Protocol):
    def put_bytes(
        self,
        *,
        scope: PrivateObjectScope,
        binding: PrivateObjectBinding,
        logical_id: str,
        content: bytes,
    ): ...

    def read_bytes(
        self,
        *,
        scope: PrivateObjectScope,
        binding: PrivateObjectBinding,
        logical_id: str,
    ) -> bytes: ...

    def delete(
        self,
        *,
        scope: PrivateObjectScope,
        binding: PrivateObjectBinding,
        logical_id: str,
        expected_checksum: str,
    ): ...


Progress = Callable[[int, int, str], None]
Runner = Callable[[dict, Progress], dict]


class _TaskCancelled(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PersistentTaskPruneReport:
    deleted: int
    blocked: int


@dataclass(frozen=True, slots=True)
class _PreparedResult:
    binding: PrivateObjectBinding
    binding_json: str
    checksum: str
    content: bytes
    logical_id: str


class SqlitePersistentTaskQueue:
    """Owner-bound durable task metadata with private object payloads.

    This is a local single-process Adapter. Task history survives API restarts,
    but Python callbacks are never deserialized or silently replayed. Work left
    queued or running by a previous process becomes ``interrupted`` and can only
    resume after a current authenticated scope supplies the runner again.

    Commands and results live in ``PrivateObjectNamespace`` objects. SQLite
    stores HMAC-bound scope/idempotency digests, lifecycle metadata and opaque
    object bindings; raw tenant and owner identifiers are never persisted.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        namespace: PrivateObjectNamespace,
        object_store: _PrivateObjectStore,
        scope_key_ring: VersionedHmacKeyRing,
        terminal_retention: timedelta = timedelta(hours=24),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if terminal_retention <= timedelta(0):
            raise ValueError("terminal_retention must be positive")
        self._db_path = db_path.absolute()
        self._namespace = namespace
        self._object_store = object_store
        self._scope_key_ring = scope_key_ring
        self._terminal_retention = terminal_retention
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = Lock()
        self._prepared = False

    def prepare(self) -> int:
        """Create a new dedicated store or validate an exact existing schema."""

        with self._lock:
            if self._prepared:
                return 0
            self._reject_link_path()
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._reject_link_path()
            existing_nonempty = (
                self._db_path.exists() and self._db_path.stat().st_size > 0
            )
            if existing_nonempty:
                self._validate_existing_schema()
            else:
                self._create_schema()
            self._validate_existing_schema()
            recovered = self._recover_active_locked()
            self._prepared = True
            return recovered

    def start(
        self,
        *,
        scope: PrivateObjectScope,
        kind: str,
        subject_id: str,
        command: Mapping[str, object],
        idempotency_key: str,
        runner: Runner,
    ) -> PersistentTaskView:
        self._require_prepared()
        kind = self._text(kind, "KIND")
        subject_id = self._text(subject_id, "SUBJECT")
        idempotency_key = self._text(idempotency_key, "IDEMPOTENCY")
        command_value = self._mapping(command, "COMMAND")
        self.prune(scope=scope)

        scope_digest = self._scope_digest(scope)
        scope_candidates = self._scope_candidates(scope)
        idempotency_candidates = self._idempotency_candidates(
            scope=scope,
            kind=kind,
            idempotency_key=idempotency_key,
        )
        subject_candidates = self._subject_candidates(
            scope=scope,
            kind=kind,
            subject_id=subject_id,
        )
        existing = self._find_idempotent(
            scope_candidates=scope_candidates,
            idempotency_candidates=idempotency_candidates,
        )
        command_bytes = self._payload_bytes(
            "command",
            {"command": command_value, "subject_id": subject_id},
        )
        command_checksum = hashlib.sha256(command_bytes).hexdigest()
        if existing is not None:
            self._assert_same_request(
                existing,
                kind=kind,
                subject_candidates=subject_candidates,
                command_checksum=command_checksum,
            )
            self._verify_command(scope=scope, row=existing)
            return self._view(scope=scope, row=existing)

        current_idempotency = idempotency_candidates[0]
        task_id = self._task_id(current_idempotency)
        command_logical_id = self._logical_id(task_id, "command", 0)
        command_binding = self._namespace.bind(
            scope=scope,
            domain=PrivateObjectDomain.BACKGROUND_JOB_RESULT,
            logical_id=command_logical_id,
        )
        try:
            receipt = self._object_store.put_bytes(
                scope=scope,
                binding=command_binding,
                logical_id=command_logical_id,
                content=command_bytes,
            )
        except PrivateObjectConflict:
            raise PersistentTaskConflict(
                "PERSISTENT_TASK_IDEMPOTENCY_CONFLICT"
            ) from None
        now = self._now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO persistent_tasks(
                        task_id, scope_digest, idempotency_digest, kind, subject_digest,
                        command_binding, command_checksum, status, message,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', '任务已持久化并排队', ?, ?)
                    """,
                    (
                        task_id,
                        scope_digest,
                        current_idempotency,
                        kind,
                        subject_candidates[0],
                        self._binding_json(command_binding),
                        receipt.checksum,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError:
            existing = self._find_idempotent(
                scope_candidates=scope_candidates,
                idempotency_candidates=idempotency_candidates,
            )
            if existing is None:
                raise PersistentTaskUnavailable(
                    "PERSISTENT_TASK_STORE_UNAVAILABLE"
                ) from None
            self._assert_same_request(
                existing,
                kind=kind,
                subject_candidates=subject_candidates,
                command_checksum=receipt.checksum,
            )
            self._verify_command(scope=scope, row=existing)
            return self._view(scope=scope, row=existing)
        except sqlite3.Error:
            raise PersistentTaskUnavailable(
                "PERSISTENT_TASK_STORE_UNAVAILABLE"
            ) from None

        Thread(
            target=self._run,
            args=(task_id, scope, runner),
            daemon=True,
        ).start()
        return self.get(task_id, scope=scope)

    def resume(
        self,
        task_id: str,
        *,
        scope: PrivateObjectScope,
        runner: Runner,
    ) -> PersistentTaskView:
        """Resume one interrupted task under a fresh authenticated scope."""

        self._require_prepared()
        row = self._row_for_scope(task_id, scope=scope)
        if row["status"] != "interrupted":
            raise PersistentTaskConflict("PERSISTENT_TASK_NOT_INTERRUPTED")
        if row["result_binding"]:
            self._delete_payload(
                scope=scope,
                task_id=task_id,
                phase="result",
                attempt=row["attempt"],
                binding_json=row["result_binding"],
                checksum=row["result_checksum"],
            )
        candidates = self._scope_candidates(scope)
        with self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE persistent_tasks
                SET status = 'queued', cancel_requested = 0, current = 0, total = 0,
                    message = '任务已重新排队', error = '', result_binding = NULL,
                    result_checksum = NULL, result_ready = 0,
                    attempt = attempt + 1, updated_at = ?
                WHERE task_id = ? AND scope_digest IN ({}) AND status = 'interrupted'
                """.format(self._placeholders(candidates)),
                (self._now(), task_id, *candidates),
            ).rowcount
        if changed != 1:
            raise PersistentTaskConflict("PERSISTENT_TASK_NOT_INTERRUPTED")
        Thread(target=self._run, args=(task_id, scope, runner), daemon=True).start()
        return self.get(task_id, scope=scope)

    def get(self, task_id: str, *, scope: PrivateObjectScope) -> PersistentTaskView:
        self._require_prepared()
        self.prune(scope=scope)
        return self._view(scope=scope, row=self._row_for_scope(task_id, scope=scope))

    def list(
        self,
        *,
        scope: PrivateObjectScope,
        kind: str | None = None,
    ) -> list[PersistentTaskView]:
        self._require_prepared()
        self.prune(scope=scope)
        candidates = self._scope_candidates(scope)
        values: list[object] = [*candidates]
        kind_sql = ""
        if kind is not None:
            kind_sql = " AND kind = ?"
            values.append(self._text(kind, "KIND"))
        values.append(self._cutoff())
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM persistent_tasks
                    WHERE scope_digest IN ({}){}
                      AND (status NOT IN ('succeeded', 'failed', 'cancelled', 'interrupted')
                           OR updated_at > ?)
                    ORDER BY created_at DESC
                    """.format(self._placeholders(candidates), kind_sql),
                    values,
                ).fetchall()
        except sqlite3.Error:
            raise PersistentTaskUnavailable(
                "PERSISTENT_TASK_STORE_UNAVAILABLE"
            ) from None
        return [self._view(scope=scope, row=row) for row in rows]

    def cancel(
        self,
        task_id: str,
        *,
        scope: PrivateObjectScope,
        result: Mapping[str, object] | None = None,
        message: str = "任务已取消",
    ) -> PersistentTaskView:
        self._require_prepared()
        with self._lock:
            row = self._row_for_scope(task_id, scope=scope)
            prepared: _PreparedResult | None = None
            if result is not None:
                prepared = self._prepare_result(
                    scope=scope,
                    task_id=task_id,
                    attempt=row["attempt"],
                    result=self._mapping(result, "RESULT"),
                )
            if row["status"] in _ACTIVE or (
                row["status"] == "cancelled" and result is not None
            ):
                candidates = self._scope_candidates(scope)
                allowed_status = (
                    "('queued', 'running')"
                    if row["status"] in _ACTIVE
                    else "('cancelled')"
                )
                with self._connect() as connection:
                    changed = connection.execute(
                        """
                        UPDATE persistent_tasks
                        SET cancel_requested = 1, status = 'cancelled', message = ?, error = '',
                            result_binding = ?, result_checksum = ?, result_ready = 0,
                            updated_at = ?
                        WHERE task_id = ? AND scope_digest IN ({})
                          AND status IN {}
                        """.format(
                            self._placeholders(candidates), allowed_status
                        ),
                        (
                            self._text(message, "MESSAGE"),
                            prepared.binding_json if prepared else None,
                            prepared.checksum if prepared else None,
                            self._now(),
                            task_id,
                            *candidates,
                        ),
                    ).rowcount
                if changed != 1:
                    raise PersistentTaskConflict(
                        "PERSISTENT_TASK_STATE_CHANGED"
                    )
                if prepared is not None:
                    self._put_prepared_result(scope=scope, prepared=prepared)
                    with self._connect() as connection:
                        changed = connection.execute(
                            """
                            UPDATE persistent_tasks SET result_ready = 1, updated_at = ?
                            WHERE task_id = ? AND scope_digest IN ({})
                              AND status = 'cancelled' AND result_binding = ?
                            """.format(self._placeholders(candidates)),
                            (
                                self._now(),
                                task_id,
                                *candidates,
                                prepared.binding_json,
                            ),
                        ).rowcount
                    if changed != 1:
                        raise PersistentTaskConflict(
                            "PERSISTENT_TASK_STATE_CHANGED"
                        )
        return self.get(task_id, scope=scope)

    def prune(self, *, scope: PrivateObjectScope) -> PersistentTaskPruneReport:
        """Remove expired payloads and metadata for one authenticated scope."""

        self._require_prepared()
        candidates = self._scope_candidates(scope)
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM persistent_tasks
                    WHERE scope_digest IN ({})
                      AND status IN ('succeeded', 'failed', 'cancelled', 'interrupted')
                      AND updated_at <= ?
                    """.format(self._placeholders(candidates)),
                    (*candidates, self._cutoff()),
                ).fetchall()
        except sqlite3.Error:
            raise PersistentTaskUnavailable(
                "PERSISTENT_TASK_STORE_UNAVAILABLE"
            ) from None
        deleted = 0
        blocked = 0
        for row in rows:
            try:
                self._delete_payload(
                    scope=scope,
                    task_id=row["task_id"],
                    phase="command",
                    attempt=0,
                    binding_json=row["command_binding"],
                    checksum=row["command_checksum"],
                )
                if row["result_binding"]:
                    self._delete_payload(
                        scope=scope,
                        task_id=row["task_id"],
                        phase="result",
                        attempt=row["attempt"],
                        binding_json=row["result_binding"],
                        checksum=row["result_checksum"],
                    )
                with self._connect() as connection:
                    connection.execute(
                        "DELETE FROM persistent_tasks WHERE task_id = ? AND updated_at <= ?",
                        (row["task_id"], self._cutoff()),
                    )
                deleted += 1
            except Exception:
                blocked += 1
        return PersistentTaskPruneReport(deleted=deleted, blocked=blocked)

    def _run(self, task_id: str, scope: PrivateObjectScope, runner: Runner) -> None:
        execution_attempt = 0

        def progress(current: int, total: int, message: str) -> None:
            if (
                type(current) is not int
                or type(total) is not int
                or current < 0
                or total < 0
            ):
                raise ValueError(
                    "persistent task progress must be non-negative integers"
                )
            self._update_active(
                task_id,
                scope=scope,
                current=current,
                total=total,
                message=self._text(message, "MESSAGE"),
                expected_attempt=execution_attempt,
            )

        try:
            row = self._claim(task_id, scope=scope)
            execution_attempt = row["attempt"]
            _, command = self._read_command(scope=scope, row=row)
            result = self._mapping(runner(command, progress), "RESULT")
            with self._lock:
                latest = self._row_for_scope(task_id, scope=scope)
                if (
                    latest["status"] not in _ACTIVE
                    or latest["cancel_requested"]
                    or latest["attempt"] != execution_attempt
                ):
                    raise _TaskCancelled
                prepared = self._prepare_result(
                    scope=scope,
                    task_id=task_id,
                    attempt=latest["attempt"],
                    result=result,
                )
                self._update_active(
                    task_id,
                    scope=scope,
                    result_binding=prepared.binding_json,
                    result_checksum=prepared.checksum,
                    result_ready=0,
                    expected_attempt=execution_attempt,
                )
                self._put_prepared_result(scope=scope, prepared=prepared)
                self._update_active(
                    task_id,
                    scope=scope,
                    status="succeeded",
                    message="处理完成",
                    error="",
                    result_ready=1,
                    expected_attempt=execution_attempt,
                )
        except _TaskCancelled:
            return
        except Exception as exc:
            try:
                self._update_active(
                    task_id,
                    scope=scope,
                    status="failed",
                    message="处理失败",
                    error=self._safe_error(exc),
                    expected_attempt=execution_attempt,
                )
            except _TaskCancelled:
                return

    def _claim(self, task_id: str, *, scope: PrivateObjectScope) -> sqlite3.Row:
        candidates = self._scope_candidates(scope)
        with self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE persistent_tasks
                SET status = 'running', message = '正在处理',
                    attempt = CASE WHEN attempt = 0 THEN 1 ELSE attempt END,
                    updated_at = ?
                WHERE task_id = ? AND scope_digest IN ({}) AND status = 'queued'
                  AND cancel_requested = 0
                """.format(self._placeholders(candidates)),
                (self._now(), task_id, *candidates),
            ).rowcount
        if changed != 1:
            raise _TaskCancelled
        return self._row_for_scope(task_id, scope=scope)

    def _update_active(
        self,
        task_id: str,
        *,
        scope: PrivateObjectScope,
        expected_attempt: int,
        **changes,
    ) -> None:
        allowed = {
            "status",
            "current",
            "total",
            "message",
            "error",
            "result_binding",
            "result_checksum",
            "result_ready",
        }
        if not changes or not set(changes).issubset(allowed):
            raise ValueError("persistent task update is invalid")
        assignments = ", ".join(f"{name} = ?" for name in changes)
        candidates = self._scope_candidates(scope)
        with self._connect() as connection:
            changed = connection.execute(
                f"""
                UPDATE persistent_tasks SET {assignments}, updated_at = ?
                WHERE task_id = ? AND scope_digest IN ({self._placeholders(candidates)})
                  AND status IN ('queued', 'running') AND cancel_requested = 0
                  AND attempt = ?
                """,
                (
                    *changes.values(),
                    self._now(),
                    task_id,
                    *candidates,
                    expected_attempt,
                ),
            ).rowcount
        if changed != 1:
            raise _TaskCancelled

    def _view(
        self,
        *,
        scope: PrivateObjectScope,
        row: sqlite3.Row,
    ) -> PersistentTaskView:
        subject_id, _ = self._read_command(scope=scope, row=row)
        result: dict = {}
        if row["result_binding"] and row["result_ready"]:
            result = self._read_payload(
                scope=scope,
                task_id=row["task_id"],
                phase="result",
                attempt=row["attempt"],
                binding_json=row["result_binding"],
                checksum=row["result_checksum"],
            )
        return PersistentTaskView(
            task_id=row["task_id"],
            kind=row["kind"],
            subject_id=subject_id,
            status=row["status"],
            current=row["current"],
            total=row["total"],
            message=row["message"],
            error=row["error"],
            result=result,
            attempt=row["attempt"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _prepare_result(
        self,
        *,
        scope: PrivateObjectScope,
        task_id: str,
        attempt: int,
        result: dict,
    ) -> _PreparedResult:
        logical_id = self._logical_id(task_id, "result", attempt)
        binding = self._namespace.bind(
            scope=scope,
            domain=PrivateObjectDomain.BACKGROUND_JOB_RESULT,
            logical_id=logical_id,
        )
        content = self._payload_bytes("result", result)
        return _PreparedResult(
            binding=binding,
            binding_json=self._binding_json(binding),
            checksum=hashlib.sha256(content).hexdigest(),
            content=content,
            logical_id=logical_id,
        )

    def _put_prepared_result(
        self,
        *,
        scope: PrivateObjectScope,
        prepared: _PreparedResult,
    ) -> None:
        try:
            receipt = self._object_store.put_bytes(
                scope=scope,
                binding=prepared.binding,
                logical_id=prepared.logical_id,
                content=prepared.content,
            )
        except PrivateObjectConflict:
            raise PersistentTaskConflict(
                "PERSISTENT_TASK_RESULT_CONFLICT"
            ) from None
        if not hmac.compare_digest(receipt.checksum, prepared.checksum):
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_UNAVAILABLE"
            )

    def _read_payload(
        self,
        *,
        scope: PrivateObjectScope,
        task_id: str,
        phase: str,
        attempt: int,
        binding_json: str,
        checksum: str,
    ) -> dict:
        if not isinstance(checksum, str) or not _CHECKSUM.fullmatch(checksum):
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_UNAVAILABLE"
            )
        binding = self._binding(binding_json)
        logical_id = self._logical_id(task_id, phase, attempt)
        try:
            content = self._object_store.read_bytes(
                scope=scope,
                binding=binding,
                logical_id=logical_id,
            )
        except Exception:
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_UNAVAILABLE"
            ) from None
        if not hmac.compare_digest(
            hashlib.sha256(content).hexdigest(), checksum
        ):
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_UNAVAILABLE"
            )
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_UNAVAILABLE"
            ) from None
        if (
            not isinstance(payload, dict)
            or set(payload) != {"payload", "phase", "schema"}
            or payload["schema"] != PERSISTENT_TASK_SCHEMA_VERSION
            or payload["phase"] != phase
            or not isinstance(payload["payload"], dict)
        ):
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_UNAVAILABLE"
            )
        return payload["payload"]

    def _delete_payload(
        self,
        *,
        scope: PrivateObjectScope,
        task_id: str,
        phase: str,
        attempt: int,
        binding_json: str,
        checksum: str,
    ) -> None:
        try:
            self._object_store.delete(
                scope=scope,
                binding=self._binding(binding_json),
                logical_id=self._logical_id(task_id, phase, attempt),
                expected_checksum=checksum,
            )
        except PrivateObjectNotFound:
            return

    def _row_for_scope(
        self,
        task_id: str,
        *,
        scope: PrivateObjectScope,
    ) -> sqlite3.Row:
        if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
            raise KeyError(task_id)
        candidates = self._scope_candidates(scope)
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM persistent_tasks
                    WHERE task_id = ? AND scope_digest IN ({})
                      AND (status NOT IN ('succeeded', 'failed', 'cancelled', 'interrupted')
                           OR updated_at > ?)
                    """.format(self._placeholders(candidates)),
                    (task_id, *candidates, self._cutoff()),
                ).fetchone()
        except sqlite3.Error:
            raise PersistentTaskUnavailable(
                "PERSISTENT_TASK_STORE_UNAVAILABLE"
            ) from None
        if row is None:
            raise KeyError(task_id)
        return row

    def _find_idempotent(
        self,
        *,
        scope_candidates: tuple[str, ...],
        idempotency_candidates: tuple[str, ...],
    ) -> sqlite3.Row | None:
        try:
            with self._connect() as connection:
                return connection.execute(
                    """
                    SELECT * FROM persistent_tasks
                    WHERE scope_digest IN ({}) AND idempotency_digest IN ({})
                      AND (status NOT IN ('succeeded', 'failed', 'cancelled', 'interrupted')
                           OR updated_at > ?)
                    ORDER BY created_at DESC LIMIT 1
                    """.format(
                        self._placeholders(scope_candidates),
                        self._placeholders(idempotency_candidates),
                    ),
                    (*scope_candidates, *idempotency_candidates, self._cutoff()),
                ).fetchone()
        except sqlite3.Error:
            raise PersistentTaskUnavailable(
                "PERSISTENT_TASK_STORE_UNAVAILABLE"
            ) from None

    @staticmethod
    def _assert_same_request(
        row: sqlite3.Row,
        *,
        kind: str,
        subject_candidates: tuple[str, ...],
        command_checksum: str,
    ) -> None:
        if (
            row["kind"] != kind
            or row["subject_digest"] not in subject_candidates
            or not hmac.compare_digest(row["command_checksum"], command_checksum)
        ):
            raise PersistentTaskConflict(
                "PERSISTENT_TASK_IDEMPOTENCY_CONFLICT"
            )

    def _verify_command(
        self,
        *,
        scope: PrivateObjectScope,
        row: sqlite3.Row,
    ) -> None:
        self._read_command(scope=scope, row=row)

    def _read_command(
        self,
        *,
        scope: PrivateObjectScope,
        row: sqlite3.Row,
    ) -> tuple[str, dict]:
        payload = self._read_payload(
            scope=scope,
            task_id=row["task_id"],
            phase="command",
            attempt=0,
            binding_json=row["command_binding"],
            checksum=row["command_checksum"],
        )
        if (
            set(payload) != {"command", "subject_id"}
            or not isinstance(payload["command"], dict)
            or not isinstance(payload["subject_id"], str)
        ):
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_UNAVAILABLE"
            )
        subject_id = self._text(payload["subject_id"], "SUBJECT")
        expected = self._subject_candidates(
            scope=scope,
            kind=row["kind"],
            subject_id=subject_id,
        )
        if row["subject_digest"] not in expected:
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_UNAVAILABLE"
            )
        return subject_id, payload["command"]

    def _recover_active_locked(self) -> int:
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE persistent_tasks
                    SET status = 'interrupted', cancel_requested = 0,
                        message = 'API 已重启，任务已中断，可重新恢复', error = '',
                        updated_at = ?
                    WHERE status IN ('queued', 'running')
                    """,
                    (self._now(),),
                )
                return cursor.rowcount
        except sqlite3.Error:
            raise PersistentTaskUnavailable(
                "PERSISTENT_TASK_STORE_UNAVAILABLE"
            ) from None

    def _scope_digest(self, scope: PrivateObjectScope) -> str:
        return self._scope_key_ring.digest(
            "persistent-task-scope", self._scope_value(scope)
        )

    def _scope_candidates(self, scope: PrivateObjectScope) -> tuple[str, ...]:
        return self._scope_key_ring.candidates(
            "persistent-task-scope", self._scope_value(scope)
        )

    def _idempotency_candidates(
        self,
        *,
        scope: PrivateObjectScope,
        kind: str,
        idempotency_key: str,
    ) -> tuple[str, ...]:
        value = json.dumps(
            {
                "idempotency_key": idempotency_key,
                "kind": kind,
                "scope": self._scope_value(scope),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return self._scope_key_ring.candidates(
            "persistent-task-idempotency", value
        )

    def _subject_candidates(
        self,
        *,
        scope: PrivateObjectScope,
        kind: str,
        subject_id: str,
    ) -> tuple[str, ...]:
        value = json.dumps(
            {
                "kind": kind,
                "scope": self._scope_value(scope),
                "subject_id": subject_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return self._scope_key_ring.candidates(
            "persistent-task-subject", value
        )

    @staticmethod
    def _scope_value(scope: PrivateObjectScope) -> str:
        if not isinstance(scope, PrivateObjectScope):
            raise ValueError("PERSISTENT_TASK_SCOPE_INVALID")
        for value in (scope.owner_id, scope.tenant_id):
            if (
                not isinstance(value, str)
                or not value
                or value != value.strip()
                or len(value) > _MAX_TEXT
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in value
                )
            ):
                raise ValueError("PERSISTENT_TASK_SCOPE_INVALID")
        return json.dumps(
            {"owner_id": scope.owner_id, "tenant_id": scope.tenant_id},
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _task_id(idempotency_digest: str) -> str:
        digest = hashlib.sha256(idempotency_digest.encode("ascii")).hexdigest()
        return f"task_{digest[:32]}"

    @staticmethod
    def _logical_id(task_id: str, phase: str, attempt: int) -> str:
        if (
            not _TASK_ID.fullmatch(task_id)
            or phase not in {"command", "result"}
            or type(attempt) is not int
            or attempt < 0
        ):
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_UNAVAILABLE"
            )
        return f"{task_id}:{phase}:{attempt}"

    @staticmethod
    def _payload_bytes(
        phase: str,
        payload: Mapping[str, object],
    ) -> bytes:
        try:
            content = json.dumps(
                {
                    "payload": dict(payload),
                    "phase": phase,
                    "schema": PERSISTENT_TASK_SCHEMA_VERSION,
                },
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_INVALID"
            ) from None
        if len(content) > _MAX_PAYLOAD_BYTES:
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_INVALID"
            )
        return content

    @staticmethod
    def _binding_json(binding: PrivateObjectBinding) -> str:
        return json.dumps(
            {
                "domain": binding.domain.value,
                "retention": binding.retention.value,
                "schema_version": binding.schema_version,
                "storage_key": binding.storage_key,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _binding(value: str) -> PrivateObjectBinding:
        try:
            decoded = json.loads(value)
            if not isinstance(decoded, dict) or set(decoded) != {
                "domain",
                "retention",
                "schema_version",
                "storage_key",
            }:
                raise ValueError
            binding = PrivateObjectBinding(
                storage_key=decoded["storage_key"],
                domain=PrivateObjectDomain(decoded["domain"]),
                retention=PrivateObjectRetention(decoded["retention"]),
                schema_version=decoded["schema_version"],
            )
            if (
                binding.domain != PrivateObjectDomain.BACKGROUND_JOB_RESULT
                or binding.retention != PrivateObjectRetention.TERMINAL_24H
                or binding.schema_version
                != PRIVATE_OBJECT_BINDING_SCHEMA_VERSION
            ):
                raise ValueError
            return binding
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise PersistentTaskPayloadError(
                "PERSISTENT_TASK_PAYLOAD_UNAVAILABLE"
            ) from None

    def _create_schema(self) -> None:
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE persistent_task_meta (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        schema_version TEXT NOT NULL
                    );
                    INSERT INTO persistent_task_meta(singleton, schema_version)
                    VALUES (1, 'm14.persistent-task.v1');

                    CREATE TABLE persistent_tasks (
                        task_id TEXT PRIMARY KEY,
                        scope_digest TEXT NOT NULL,
                        idempotency_digest TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        subject_digest TEXT NOT NULL,
                        command_binding TEXT NOT NULL,
                        command_checksum TEXT NOT NULL,
                        result_binding TEXT,
                        result_checksum TEXT,
                        result_ready INTEGER NOT NULL DEFAULT 0 CHECK (
                            result_ready IN (0, 1)
                        ),
                        status TEXT NOT NULL CHECK (
                            status IN (
                                'queued', 'running', 'succeeded', 'failed',
                                'cancelled', 'interrupted'
                            )
                        ),
                        current INTEGER NOT NULL DEFAULT 0 CHECK (current >= 0),
                        total INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),
                        message TEXT NOT NULL DEFAULT '',
                        error TEXT NOT NULL DEFAULT '',
                        attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
                        cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (
                            cancel_requested IN (0, 1)
                        ),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(scope_digest, idempotency_digest)
                    );
                    CREATE INDEX persistent_tasks_scope_kind_created
                    ON persistent_tasks(scope_digest, kind, created_at DESC);
                    """
                )
        except sqlite3.Error:
            raise PersistentTaskUnavailable(
                "PERSISTENT_TASK_STORE_UNAVAILABLE"
            ) from None

    def _validate_existing_schema(self) -> None:
        try:
            with self._connect(read_only=True) as connection:
                tables = frozenset(
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                    if not row[0].startswith("sqlite_")
                )
                version_row = connection.execute(
                    "SELECT schema_version FROM persistent_task_meta WHERE singleton = 1"
                ).fetchone()
                columns = tuple(
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(persistent_tasks)"
                    )
                )
        except sqlite3.Error:
            raise PersistentTaskUnavailable(
                "PERSISTENT_TASK_SCHEMA_INVALID"
            ) from None
        expected_columns = (
            "task_id",
            "scope_digest",
            "idempotency_digest",
            "kind",
            "subject_digest",
            "command_binding",
            "command_checksum",
            "result_binding",
            "result_checksum",
            "result_ready",
            "status",
            "current",
            "total",
            "message",
            "error",
            "attempt",
            "cancel_requested",
            "created_at",
            "updated_at",
        )
        if (
            tables != _SCHEMA_TABLES
            or version_row is None
            or version_row[0] != PERSISTENT_TASK_SCHEMA_VERSION
            or columns != expected_columns
        ):
            raise PersistentTaskUnavailable("PERSISTENT_TASK_SCHEMA_INVALID")

    @contextmanager
    def _connect(
        self,
        *,
        read_only: bool = False,
    ) -> Iterator[sqlite3.Connection]:
        self._reject_link_path()
        try:
            if read_only:
                connection = sqlite3.connect(
                    f"file:{self._db_path.as_posix()}?mode=ro",
                    uri=True,
                    timeout=5,
                )
            else:
                connection = sqlite3.connect(self._db_path, timeout=5)
        except sqlite3.Error:
            raise PersistentTaskUnavailable(
                "PERSISTENT_TASK_STORE_UNAVAILABLE"
            ) from None
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            if not read_only:
                connection.commit()
        except BaseException:
            if not read_only:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _reject_link_path(self) -> None:
        for candidate in (self._db_path, *self._db_path.parents):
            if candidate.exists() and is_link_or_reparse(candidate):
                raise PersistentTaskUnavailable("PERSISTENT_TASK_PATH_INVALID")

    def _require_prepared(self) -> None:
        if not self._prepared:
            raise PersistentTaskUnavailable(
                "PERSISTENT_TASK_STORE_NOT_PREPARED"
            )

    def _now(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("persistent task clock must be timezone-aware")
        return value.astimezone(UTC).isoformat()

    def _cutoff(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("persistent task clock must be timezone-aware")
        return (value.astimezone(UTC) - self._terminal_retention).isoformat()

    @staticmethod
    def _placeholders(values: tuple[str, ...]) -> str:
        return ",".join("?" for _ in values)

    @staticmethod
    def _text(value: str, label: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > _MAX_TEXT
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError(f"PERSISTENT_TASK_{label}_INVALID")
        return value

    @staticmethod
    def _mapping(value: Mapping[str, object], label: str) -> dict:
        if not isinstance(value, Mapping):
            raise PersistentTaskPayloadError(
                f"PERSISTENT_TASK_{label}_INVALID"
            )
        return dict(value)

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, PersistentTaskPayloadError):
            return str(exc)
        return "任务执行失败"
