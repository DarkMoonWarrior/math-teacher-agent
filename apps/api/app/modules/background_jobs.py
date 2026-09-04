from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Lock, Thread
from typing import Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class BackgroundJobView(BaseModel):
    job_id: str
    kind: str
    subject_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    current: int = 0
    total: int = 0
    message: str = ""
    error: str = ""
    result: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str


Progress = Callable[[int, int, str], None]
Runner = Callable[[Progress], dict]


class _BackgroundJobCancelled(Exception):
    """Internal control flow used to stop a runner before it commits a result."""


class BackgroundJobRegistry:
    """Small process-local registry for slow OCR/model operations.

    The source data remains durable in each domain database. Jobs are deliberately
    transient: after an API restart the UI can simply start the operation again.
    """

    def __init__(
        self,
        *,
        terminal_retention: timedelta = timedelta(hours=24),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if terminal_retention <= timedelta(0):
            raise ValueError("terminal_retention must be positive")
        self._lock = Lock()
        self._jobs: dict[str, dict] = {}
        self._terminal_retention = terminal_retention
        self._clock = clock or (lambda: datetime.now(UTC))

    def start(
        self, *, kind: str, subject_id: str, owner_id: str, runner: Runner
    ) -> BackgroundJobView:
        now = self._now()
        job_id = f"job_{uuid4().hex[:16]}"
        with self._lock:
            self._prune_expired_locked()
            self._jobs[job_id] = {
                "job_id": job_id, "kind": kind, "subject_id": subject_id,
                "owner_id": owner_id,
                "cancel_requested": False,
                "status": "queued", "current": 0, "total": 0,
                "message": "任务已排队", "error": "", "result": {},
                "created_at": now, "updated_at": now,
            }
        Thread(target=self._run, args=(job_id, runner), daemon=True).start()
        return self.get(job_id, owner_id=owner_id)

    def get(self, job_id: str, *, owner_id: str) -> BackgroundJobView:
        with self._lock:
            self._prune_expired_locked()
            value = self._jobs.get(job_id)
            if value is None or value["owner_id"] != owner_id:
                raise KeyError(job_id)
            public_value = self._public_value(value)
            return BackgroundJobView.model_validate(public_value)

    def list(self, *, owner_id: str, kind: str | None = None) -> list[BackgroundJobView]:
        """Return the owner's jobs newest-first without exposing registry internals."""
        with self._lock:
            self._prune_expired_locked()
            values = [
                deepcopy(value)
                for value in self._jobs.values()
                if value["owner_id"] == owner_id
                and (kind is None or value["kind"] == kind)
            ]
        values.sort(key=lambda value: value["created_at"], reverse=True)
        return [
            BackgroundJobView.model_validate(
                self._public_value(value)
            )
            for value in values
        ]

    def latest(self, *, owner_id: str, kind: str) -> BackgroundJobView:
        jobs = self.list(owner_id=owner_id, kind=kind)
        if not jobs:
            raise KeyError(kind)
        return jobs[0]

    def cancel(
        self,
        job_id: str,
        *,
        owner_id: str,
        result: dict | None = None,
        message: str = "任务已取消",
    ) -> BackgroundJobView:
        """Request owner-scoped cancellation without exposing partial results.

        A provider call already in flight cannot always be interrupted. The runner's
        next progress checkpoint raises before any domain write, so cancellation is
        still a reliable no-commit boundary.
        """
        with self._lock:
            self._prune_expired_locked()
            value = self._jobs.get(job_id)
            if value is None or value["owner_id"] != owner_id:
                raise KeyError(job_id)
            if value["status"] in {"queued", "running"}:
                value.update(
                    cancel_requested=True,
                    status="cancelled",
                    message=message,
                    error="",
                    result=deepcopy(result or {}),
                    updated_at=self._now(),
                )
            elif value["status"] == "cancelled" and result is not None:
                value.update(
                    message=message,
                    result=deepcopy(result),
                    updated_at=self._now(),
                )
            return BackgroundJobView.model_validate(self._public_value(value))

    def clear(self) -> None:
        """Drop transient records; intended for process teardown and tests."""
        with self._lock:
            self._jobs.clear()

    @staticmethod
    def _public_value(value: dict) -> dict:
        return {
            key: item
            for key, item in deepcopy(value).items()
            if key not in {"owner_id", "cancel_requested"}
        }

    def _start_running(self, job_id: str) -> None:
        with self._lock:
            value = self._jobs.get(job_id)
            if value is None:
                raise _BackgroundJobCancelled
            if value["cancel_requested"]:
                raise _BackgroundJobCancelled
            value.update(status="running", message="正在处理")
            value["updated_at"] = self._now()

    def _update_active(self, job_id: str, **values) -> None:
        with self._lock:
            value = self._jobs.get(job_id)
            if value is None:
                raise _BackgroundJobCancelled
            if value["cancel_requested"]:
                raise _BackgroundJobCancelled
            value.update(values)
            value["updated_at"] = self._now()

    def _finish_cancelled(self, job_id: str) -> None:
        with self._lock:
            value = self._jobs.get(job_id)
            if value is None:
                return
            value.update(
                cancel_requested=True,
                status="cancelled",
                message=value["message"] or "任务已取消",
                error="",
                updated_at=self._now(),
            )

    def _now(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("background job clock must be timezone-aware")
        return value.isoformat()

    def _prune_expired_locked(self) -> None:
        current = self._clock()
        if current.tzinfo is None:
            raise ValueError("background job clock must be timezone-aware")
        cutoff = current - self._terminal_retention
        terminal = {"succeeded", "failed", "cancelled"}
        expired: list[str] = []
        for job_id, value in self._jobs.items():
            if value["status"] not in terminal:
                continue
            try:
                updated_at = datetime.fromisoformat(value["updated_at"])
            except (TypeError, ValueError):
                continue
            if updated_at.tzinfo is not None and updated_at <= cutoff:
                expired.append(job_id)
        for job_id in expired:
            del self._jobs[job_id]

    def _run(self, job_id: str, runner: Runner) -> None:
        def progress(current: int, total: int, message: str) -> None:
            self._update_active(job_id, current=current, total=total, message=message)

        try:
            self._start_running(job_id)
            result = runner(progress)
            self._update_active(
                job_id, status="succeeded", message="处理完成", result=result
            )
        except _BackgroundJobCancelled:
            self._finish_cancelled(job_id)
        except Exception as exc:  # boundary: the API reports the domain error to the UI
            try:
                self._update_active(
                    job_id, status="failed", message="处理失败", error=str(exc)
                )
            except _BackgroundJobCancelled:
                self._finish_cancelled(job_id)
