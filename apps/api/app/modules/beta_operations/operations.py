from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass

from app.modules.beta_operations.schemas import (
    OperationalCapability,
    OperationalEvent,
)


logger = logging.getLogger("uvicorn.error.beta_operations")
logger.setLevel(logging.INFO)


@dataclass(frozen=True)
class _OperationContext:
    request_id: str
    capability: OperationalCapability
    method: str
    started_ns: int


class PrivacySafeOperations:
    """Reduce HTTP activity to an allow-listed, content-free event.

    The interface never accepts headers, query strings, request bodies, response
    bodies, teacher identifiers or exception messages, so those values cannot be
    accidentally written by this module.
    """

    _PREFIXES: tuple[tuple[str, OperationalCapability], ...] = (
        ("/api/v1/beta-session", "access"),
        ("/api/v1/agent/question-authoring", "authoring"),
        ("/api/v1/agent/private-library", "library"),
        ("/api/v1/agent/search", "search"),
        ("/api/v1/agent/solve", "solve"),
        ("/api/v1/question-capture", "solve"),
        ("/api/v1/solutions", "solve"),
        ("/api/v1/lesson-plans", "lesson"),
        ("/api/v1/exam-papers", "paper"),
        ("/api/v1/teacher-memory", "teacher_memory"),
        ("/api/v1/imports", "library"),
        ("/api/v1/library", "library"),
    )

    def begin(self, *, method: str, path: str) -> _OperationContext:
        return _OperationContext(
            request_id=f"op_{uuid.uuid4().hex}",
            capability=self.classify(path),
            method=method if method in {"GET", "POST", "PUT", "PATCH", "DELETE"} else "OTHER",
            started_ns=time.perf_counter_ns(),
        )

    def complete(self, context: _OperationContext, *, status_code: int) -> OperationalEvent:
        if status_code >= 500:
            outcome = "server_error"
        elif status_code >= 400:
            outcome = "client_error"
        else:
            outcome = "success"
        event = OperationalEvent(
            request_id=context.request_id,
            capability=context.capability,
            method=context.method,
            outcome=outcome,
            status_code=status_code,
            error_class="" if status_code < 400 else f"HTTP_{status_code}",
            duration_ms=max(0, (time.perf_counter_ns() - context.started_ns) // 1_000_000),
        )
        payload = event.model_dump()
        logger.info(
            "beta_operation %s",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            extra={"operation_event": payload},
        )
        return event

    @classmethod
    def classify(cls, path: str) -> OperationalCapability:
        if path in {"/health", "/ready"}:
            return "system"
        for prefix, capability in cls._PREFIXES:
            if path == prefix or path.startswith(f"{prefix}/"):
                return capability
        return "shared"


class PrivacySafeOperationsMiddleware:
    def __init__(self, app, *, operations: PrivacySafeOperations) -> None:
        self.app = app
        self.operations = operations

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        context = self.operations.begin(
            method=str(scope.get("method", "OTHER")).upper(),
            path=str(scope.get("path", "")),
        )
        status_code = 500

        async def send_with_request_id(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", context.request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            self.operations.complete(context, status_code=status_code)
