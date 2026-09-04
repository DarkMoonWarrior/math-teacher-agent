"""Server-scoped model session names; browser aliases are never runtime selectors."""
import hashlib
import hmac
import json
import secrets
from typing import Literal

from fastapi import HTTPException


class TeacherAgentSessions:
    """Stateless, process-lifetime session isolation by teacher AND workflow.

    A browser alias deterministically maps to a signed opaque name in one scope.
    A returned signed name can only be reused within that same scope. The secret
    never leaves this process; restart invalidates old signed names, not content.
    """

    _prefix = "tch_scoped_"

    def __init__(self) -> None:
        self._secret = secrets.token_bytes(32)

    def resolve(
        self,
        *,
        owner_id: str,
        workflow: Literal["search", "solve", "authoring", "library"],
        client_session_id: str | None,
    ) -> str:
        scope = json.dumps([owner_id, workflow], ensure_ascii=False, separators=(",", ":"))

        def digest(value: str) -> str:
            return hmac.new(self._secret, value.encode("utf-8"), hashlib.sha256).hexdigest()

        if client_session_id and client_session_id.startswith(self._prefix):
            parts = client_session_id[len(self._prefix):].split("_")
            if len(parts) == 2 and hmac.compare_digest(
                parts[1].encode("utf-8"), digest(scope + ":session:" + parts[0]).encode("ascii")
            ):
                return client_session_id
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "SESSION_NOT_AVAILABLE",
                    "message": "该任务会话不可用，请清空当前任务后重试。",
                },
            )
        nonce = (
            digest(scope + ":alias:" + client_session_id)[:32]
            if client_session_id else secrets.token_hex(16)
        )
        return self._prefix + nonce + "_" + digest(scope + ":session:" + nonce)


agent_sessions = TeacherAgentSessions()
