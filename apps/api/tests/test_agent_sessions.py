import pytest
from fastapi import HTTPException

from app.core.agent_sessions import TeacherAgentSessions


@pytest.mark.parametrize("workflow", ["search", "solve", "authoring", "library"])
def test_session_alias_is_scoped_signed_and_reusable_only_by_owner(workflow):
    sessions = TeacherAgentSessions()
    def resolve(owner, alias):
        return sessions.resolve(owner_id=owner, workflow=workflow, client_session_id=alias)

    alpha = resolve("synthetic-alpha", "browser-alias")
    beta = resolve("synthetic-beta", "browser-alias")
    assert alpha != beta
    assert resolve("synthetic-alpha", "browser-alias") == alpha
    assert resolve("synthetic-alpha", alpha) == alpha
    assert len(alpha) <= 160
    assert "synthetic-alpha" not in alpha
    with pytest.raises(HTTPException) as error:
        resolve("synthetic-beta", alpha)
    assert error.value.status_code == 404
    assert alpha not in str(error.value.detail)
    assert resolve("synthetic-alpha", None) != resolve("synthetic-alpha", None)


def test_workflows_restart_and_tampering_cannot_reuse_existing_model_context():
    sessions = TeacherAgentSessions()
    token = sessions.resolve(owner_id="alpha", workflow="library", client_session_id="alias")
    for service, workflow, value in (
        (sessions, "search", token),
        (TeacherAgentSessions(), "library", token),
        (sessions, "library", token + "x"),
        (sessions, "library", "tch_scoped_伪造_会话"),
    ):
        with pytest.raises(HTTPException) as error:
            service.resolve(owner_id="alpha", workflow=workflow, client_session_id=value)
        assert error.value.status_code == 404
