from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest

from app.modules.account_identity import VersionedHmacKeyRing
from app.modules.persistent_tasks import (
    PersistentTaskConflict,
    PersistentTaskPayloadError,
    PersistentTaskUnavailable,
    SqlitePersistentTaskQueue,
)
from app.modules.private_object_storage import (
    FilesystemPrivateObjectStore,
    PrivateObjectNamespace,
    PrivateObjectScope,
)


_OBJECT_SECRET = "persistent-object-secret-2026-09-0001"
_SCOPE_SECRET = "persistent-scope-secret-2026-09-00001"


class _BlockFirstResultPut:
    def __init__(self, delegate: FilesystemPrivateObjectStore) -> None:
        self._delegate = delegate
        self.written = Event()
        self.release = Event()
        self._blocked = False

    def put_bytes(self, **kwargs):
        receipt = self._delegate.put_bytes(**kwargs)
        logical_id = kwargs["logical_id"]
        if logical_id.endswith(":result:1") and not self._blocked:
            self._blocked = True
            self.written.set()
            self.release.wait(timeout=2)
        return receipt

    def read_bytes(self, **kwargs):
        return self._delegate.read_bytes(**kwargs)

    def delete(self, **kwargs):
        return self._delegate.delete(**kwargs)


def _key_ring(
    *,
    key_id: str,
    secret: str,
    previous: dict[str, str] | None = None,
) -> VersionedHmacKeyRing:
    return VersionedHmacKeyRing(
        current_key_id=key_id,
        current_secret=secret,
        previous_keys=previous,
    )


def _queue(
    tmp_path: Path,
    *,
    clock=None,
    object_ring: VersionedHmacKeyRing | None = None,
    scope_ring: VersionedHmacKeyRing | None = None,
) -> SqlitePersistentTaskQueue:
    namespace = PrivateObjectNamespace(
        key_ring=object_ring
        or _key_ring(key_id="object-current", secret=_OBJECT_SECRET)
    )
    store = FilesystemPrivateObjectStore(
        root=tmp_path / "objects",
        namespace=namespace,
        private_storage_confirmed=True,
    )
    store.prepare()
    queue = SqlitePersistentTaskQueue(
        db_path=tmp_path / "tasks.sqlite3",
        namespace=namespace,
        object_store=store,
        scope_key_ring=scope_ring
        or _key_ring(key_id="scope-current", secret=_SCOPE_SECRET),
        clock=clock,
    )
    return queue


def _scope(*, tenant="tenant-a", owner="owner-a") -> PrivateObjectScope:
    return PrivateObjectScope(tenant_id=tenant, owner_id=owner)


def _wait_for(queue, task_id: str, *, scope, status: str):
    for _ in range(200):
        current = queue.get(task_id, scope=scope)
        if current.status == status:
            return current
        time.sleep(0.01)
    raise AssertionError(f"task did not reach {status}: {current.model_dump()}")


def test_task_payloads_are_private_objects_and_scope_is_not_persisted(
    tmp_path: Path,
) -> None:
    queue = _queue(tmp_path)
    assert queue.prepare() == 0
    secret_command = "仅 owner-a 可见的函数命题"
    private_subject = "仅本人可见的资源标识"
    task = queue.start(
        scope=_scope(),
        kind="question_authoring",
        subject_id=private_subject,
        command={"instruction": secret_command},
        idempotency_key="request-1",
        runner=lambda command, progress: {"echo": command["instruction"]},
    )
    completed = _wait_for(
        queue,
        task.task_id,
        scope=_scope(),
        status="succeeded",
    )

    assert completed.result == {"echo": secret_command}
    assert completed.subject_id == private_subject
    database_bytes = (tmp_path / "tasks.sqlite3").read_bytes()
    for private_value in (
        b"tenant-a",
        b"owner-a",
        secret_command.encode("utf-8"),
        private_subject.encode("utf-8"),
    ):
        assert private_value not in database_bytes
    with pytest.raises(KeyError):
        queue.get(task.task_id, scope=_scope(owner="owner-b"))
    with pytest.raises(KeyError):
        queue.get(task.task_id, scope=_scope(tenant="tenant-b"))


def test_idempotency_reuses_same_task_and_rejects_changed_command(
    tmp_path: Path,
) -> None:
    queue = _queue(tmp_path)
    queue.prepare()
    executions = []

    def runner(command, progress):
        executions.append(command)
        return {"ok": True}

    first = queue.start(
        scope=_scope(),
        kind="ocr",
        subject_id="resource-1",
        command={"revision": 1},
        idempotency_key="same-request",
        runner=runner,
    )
    _wait_for(queue, first.task_id, scope=_scope(), status="succeeded")
    repeated = queue.start(
        scope=_scope(),
        kind="ocr",
        subject_id="resource-1",
        command={"revision": 1},
        idempotency_key="same-request",
        runner=runner,
    )

    assert repeated.task_id == first.task_id
    assert len(executions) == 1
    with pytest.raises(
        PersistentTaskConflict,
        match="^PERSISTENT_TASK_IDEMPOTENCY_CONFLICT$",
    ):
        queue.start(
            scope=_scope(),
            kind="ocr",
            subject_id="resource-1",
            command={"revision": 2},
            idempotency_key="same-request",
            runner=runner,
        )


def test_restart_marks_active_work_interrupted_and_requires_explicit_resume(
    tmp_path: Path,
) -> None:
    entered = Event()
    release = Event()
    first_queue = _queue(tmp_path)
    first_queue.prepare()

    def blocked_runner(command, progress):
        entered.set()
        release.wait(timeout=2)
        progress(1, 1, "旧进程不应再提交")
        return {"process": "old"}

    task = first_queue.start(
        scope=_scope(),
        kind="repair",
        subject_id="resource-2",
        command={"revision": 3},
        idempotency_key="restart-request",
        runner=blocked_runner,
    )
    assert entered.wait(timeout=1)

    second_queue = _queue(tmp_path)
    assert second_queue.prepare() == 1
    interrupted = second_queue.get(task.task_id, scope=_scope())
    assert interrupted.status == "interrupted"
    assert "可重新恢复" in interrupted.message
    release.set()

    resumed = second_queue.resume(
        task.task_id,
        scope=_scope(),
        runner=lambda command, progress: {
            "process": "new",
            "revision": command["revision"],
        },
    )
    completed = _wait_for(
        second_queue,
        resumed.task_id,
        scope=_scope(),
        status="succeeded",
    )
    assert completed.result == {"process": "new", "revision": 3}
    assert completed.attempt == 2


def test_resume_deletes_unpublished_result_and_fences_old_worker(
    tmp_path: Path,
) -> None:
    namespace = PrivateObjectNamespace(
        key_ring=_key_ring(key_id="object-current", secret=_OBJECT_SECRET)
    )
    store = FilesystemPrivateObjectStore(
        root=tmp_path / "objects",
        namespace=namespace,
        private_storage_confirmed=True,
    )
    store.prepare()
    blocked_store = _BlockFirstResultPut(store)
    first_queue = SqlitePersistentTaskQueue(
        db_path=tmp_path / "tasks.sqlite3",
        namespace=namespace,
        object_store=blocked_store,
        scope_key_ring=_key_ring(
            key_id="scope-current",
            secret=_SCOPE_SECRET,
        ),
    )
    first_queue.prepare()
    task = first_queue.start(
        scope=_scope(),
        kind="ocr",
        subject_id="resource-crash-window",
        command={"revision": 1},
        idempotency_key="crash-window-request",
        runner=lambda command, progress: {"process": "old"},
    )
    assert blocked_store.written.wait(timeout=1)

    with sqlite3.connect(tmp_path / "tasks.sqlite3") as connection:
        result_binding, result_ready = connection.execute(
            "SELECT result_binding, result_ready FROM persistent_tasks WHERE task_id = ?",
            (task.task_id,),
        ).fetchone()
    old_storage_key = json.loads(result_binding)["storage_key"]
    old_result_path = (tmp_path / "objects").joinpath(*old_storage_key.split("/"))
    assert result_ready == 0
    assert old_result_path.exists()

    second_queue = SqlitePersistentTaskQueue(
        db_path=tmp_path / "tasks.sqlite3",
        namespace=namespace,
        object_store=store,
        scope_key_ring=_key_ring(
            key_id="scope-current",
            secret=_SCOPE_SECRET,
        ),
    )
    assert second_queue.prepare() == 1
    try:
        resumed = second_queue.resume(
            task.task_id,
            scope=_scope(),
            runner=lambda command, progress: {"process": "new"},
        )
        assert not old_result_path.exists()
    finally:
        blocked_store.release.set()

    completed = _wait_for(
        second_queue,
        resumed.task_id,
        scope=_scope(),
        status="succeeded",
    )
    assert completed.result == {"process": "new"}
    assert completed.attempt == 2


def test_cancel_is_scope_bound_and_prevents_late_worker_commit(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    queue.prepare()
    entered = Event()
    release = Event()

    def runner(command, progress):
        entered.set()
        release.wait(timeout=2)
        progress(1, 1, "准备提交")
        return {"late": True}

    task = queue.start(
        scope=_scope(),
        kind="authoring",
        subject_id="statement-1",
        command={"brief": "函数题"},
        idempotency_key="cancel-request",
        runner=runner,
    )
    assert entered.wait(timeout=1)
    with pytest.raises(KeyError):
        queue.cancel(task.task_id, scope=_scope(owner="owner-b"))
    cancelled = queue.cancel(
        task.task_id,
        scope=_scope(),
        result={"statement_preserved": True},
        message="题面已保留",
    )
    release.set()
    time.sleep(0.05)

    final = queue.get(task.task_id, scope=_scope())
    assert cancelled.status == final.status == "cancelled"
    assert final.result == {"statement_preserved": True}
    assert final.message == "题面已保留"


def test_terminal_retention_hides_and_physically_prunes_payloads(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 9, 12, tzinfo=UTC)]
    queue = _queue(tmp_path, clock=lambda: now[0])
    queue.prepare()
    task = queue.start(
        scope=_scope(),
        kind="ocr",
        subject_id="resource-3",
        command={"private": "command"},
        idempotency_key="retention-request",
        runner=lambda command, progress: {"private": "result"},
    )
    _wait_for(queue, task.task_id, scope=_scope(), status="succeeded")
    now[0] += timedelta(hours=25)

    report = queue.prune(scope=_scope())

    assert report.deleted == 1
    assert report.blocked == 0
    assert queue.list(scope=_scope()) == []
    with pytest.raises(KeyError):
        queue.get(task.task_id, scope=_scope())
    with sqlite3.connect(tmp_path / "tasks.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM persistent_tasks").fetchone()[0] == 0


def test_key_rotation_reads_existing_task_without_rewriting_private_identity(
    tmp_path: Path,
) -> None:
    old_object = _key_ring(key_id="object-old", secret=_OBJECT_SECRET)
    old_scope = _key_ring(key_id="scope-old", secret=_SCOPE_SECRET)
    first = _queue(tmp_path, object_ring=old_object, scope_ring=old_scope)
    first.prepare()
    task = first.start(
        scope=_scope(),
        kind="ocr",
        subject_id="resource-4",
        command={"revision": 1},
        idempotency_key="rotation-request",
        runner=lambda command, progress: {"readable": True},
    )
    _wait_for(first, task.task_id, scope=_scope(), status="succeeded")

    rotated = _queue(
        tmp_path,
        object_ring=_key_ring(
            key_id="object-new",
            secret="persistent-object-secret-2026-10-0002",
            previous={"object-old": _OBJECT_SECRET},
        ),
        scope_ring=_key_ring(
            key_id="scope-new",
            secret="persistent-scope-secret-2026-10-00002",
            previous={"scope-old": _SCOPE_SECRET},
        ),
    )
    assert rotated.prepare() == 0

    assert rotated.get(task.task_id, scope=_scope()).result == {"readable": True}


def test_unknown_existing_sqlite_schema_is_never_adopted(tmp_path: Path) -> None:
    path = tmp_path / "tasks.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated(secret TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('keep me')")
    queue = _queue(tmp_path)

    with pytest.raises(
        PersistentTaskUnavailable,
        match="^PERSISTENT_TASK_SCHEMA_INVALID$",
    ):
        queue.prepare()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT secret FROM unrelated").fetchone()[0] == "keep me"


def test_tampered_private_result_fails_closed(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    queue.prepare()
    task = queue.start(
        scope=_scope(),
        kind="ocr",
        subject_id="resource-5",
        command={"revision": 1},
        idempotency_key="tamper-request",
        runner=lambda command, progress: {"trusted": "result"},
    )
    _wait_for(queue, task.task_id, scope=_scope(), status="succeeded")
    with sqlite3.connect(tmp_path / "tasks.sqlite3") as connection:
        binding = connection.execute(
            "SELECT result_binding FROM persistent_tasks WHERE task_id = ?",
            (task.task_id,),
        ).fetchone()[0]
    storage_key = __import__("json").loads(binding)["storage_key"]
    target = (tmp_path / "objects").joinpath(*storage_key.split("/"))
    envelope = target.read_bytes()
    target.write_bytes(envelope[:-1] + b"X")

    with pytest.raises(
        PersistentTaskPayloadError,
        match="^PERSISTENT_TASK_PAYLOAD_UNAVAILABLE$",
    ):
        queue.get(task.task_id, scope=_scope())


def test_runner_failure_does_not_persist_or_expose_private_exception_text(
    tmp_path: Path,
) -> None:
    queue = _queue(tmp_path)
    queue.prepare()
    secret = "不得写入任务元数据的私人题面"

    def runner(command, progress):
        raise RuntimeError(secret)

    task = queue.start(
        scope=_scope(),
        kind="authoring",
        subject_id="resource-6",
        command={"revision": 1},
        idempotency_key="failure-request",
        runner=runner,
    )
    failed = _wait_for(queue, task.task_id, scope=_scope(), status="failed")

    assert failed.error == "任务执行失败"
    assert secret.encode("utf-8") not in (tmp_path / "tasks.sqlite3").read_bytes()


@pytest.mark.parametrize(
    "scope",
    [
        PrivateObjectScope(tenant_id="", owner_id="owner-a"),
        PrivateObjectScope(tenant_id="tenant-a", owner_id=" owner-a"),
    ],
)
def test_invalid_scope_is_rejected_before_database_lookup(
    tmp_path: Path,
    scope: PrivateObjectScope,
) -> None:
    queue = _queue(tmp_path)
    queue.prepare()

    with pytest.raises(ValueError, match="^PERSISTENT_TASK_SCOPE_INVALID$"):
        queue.list(scope=scope)
