"""Exhaustive dependency coverage, including routes omitted from OpenAPI.

This locks down entry authentication, not business-level ownership by itself.
Owner-resource tests in each module and the real-cookie rehearsals remain required.
"""
import re
from datetime import timedelta

import pytest

from app.main import app
from app.core.identity import get_current_teacher, require_local_legacy_access
from app.routes.internal_agent_tools import _require_tool_gateway_token
from app.modules.beta_access import BetaAccess, BetaParticipant
from app.modules.beta_access.dependencies import get_beta_access
from tests.test_beta_lifecycle import beta_lifecycle  # noqa: F401


PUBLIC = {
    ("GET", "/health"), ("GET", "/ready"),
    ("GET", "/api/v1/curriculum/tree"), ("GET", "/api/v1/curriculum/search"),
    ("GET", "/api/v1/curriculum/nodes/{node_id}"),
    ("GET", "/api/v1/beta-session"), ("POST", "/api/v1/beta-session"),
    ("DELETE", "/api/v1/beta-session"),
}

# Authenticated teachers retain access to the disclosure, export and deletion
# rights even when their product capability allow-list is empty.
ACCOUNT_RIGHTS = {
    ("GET", "/api/v1/beta-validation/notice"),
    ("POST", "/api/v1/beta-validation/participation"),
    ("GET", "/api/v1/beta-validation/export"),
    ("DELETE", "/api/v1/beta-validation/participation"),
}


def _routes():
    # FastAPI's deferred router contexts include parent dependencies/prefixes.
    # The fallback also supports older, eagerly materialized APIRoutes.
    return [item for route in app.routes
            for item in (route.effective_route_contexts()
                         if hasattr(route, "effective_route_contexts") else [route])
            if hasattr(item, "dependant")]


def _dependencies(dependant):
    return {dependant.call} | {call for child in dependant.dependencies for call in _dependencies(child)}


def test_every_business_route_has_an_explicit_access_boundary():
    seen_public = set()
    internal_count = 0
    for route in _routes():
        calls = _dependencies(route.dependant)
        for method in route.methods:
            key = (method, route.path)
            if key in PUBLIC:
                seen_public.add(key)
            elif route.path.startswith("/internal/"):
                internal_count += 1
                assert _require_tool_gateway_token in calls, key
                assert not route.include_in_schema, key
            else:
                assert route.path.startswith("/api/v1/"), key
                assert calls & {get_current_teacher, require_local_legacy_access}, key
                if require_local_legacy_access not in calls:
                    # Owner context must be injected into the actual endpoint,
                    # not merely into an ancestor capability dependency.
                    if key != ("GET", "/api/v1/exam-papers/templates"):
                        assert get_current_teacher in {d.call for d in route.dependant.dependencies}, key
    assert seen_public == PUBLIC
    assert internal_count == 9


@pytest.mark.parametrize("state", ["anonymous", "expired", "revoked", "no_capabilities"])
def test_denied_requests_are_rejected_across_the_route_inventory(beta_lifecycle, monkeypatch, state):
    clients, settings, now, *_ = beta_lifecycle
    client = clients["anonymous"] if state == "anonymous" else clients["alpha"]
    if state == "expired":
        now[0] += timedelta(hours=2)
    elif state == "revoked":
        token = client.cookies.get(settings.beta_session_cookie_name)
        assert client.delete("/api/v1/beta-session").status_code == 200
        client.cookies.set(settings.beta_session_cookie_name, token)
    elif state == "no_capabilities":
        access = BetaAccess(database_path=settings.beta_session_db,
                            participants={"synthetic-empty": BetaParticipant(
                                teacher_id="empty", display_label="empty", capabilities=[])},
                            session_ttl=timedelta(hours=1), clock=lambda: now[0])
        monkeypatch.setitem(app.dependency_overrides, get_beta_access, lambda: access)
        assert client.post("/api/v1/beta-session", json={"access_code": "synthetic-empty"}).status_code == 200
    for route in _routes():
        for method in route.methods:
            if (method, route.path) in PUBLIC or route.path.startswith("/internal/"):
                continue
            # The graph assertion runs before any HTTP call, so a newly unguarded
            # route cannot accidentally execute a real business dependency here.
            calls = _dependencies(route.dependant)
            assert calls & {get_current_teacher, require_local_legacy_access}, route.path
            path = re.sub(r"\{[^}]+\}", "synthetic-missing", route.path)
            response = client.request(method, path, json={})
            if state == "no_capabilities" and (method, route.path) in ACCOUNT_RIGHTS:
                assert response.status_code in (200, 409, 422, 503), route.path
            else:
                assert response.status_code in (401, 403), (
                    state,
                    method,
                    route.path,
                    response.status_code,
                )
                if state == "no_capabilities":
                    assert response.status_code == 403, route.path
            assert response.headers["cache-control"] == "private, no-store"
