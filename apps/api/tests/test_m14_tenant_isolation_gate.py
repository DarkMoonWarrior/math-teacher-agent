"""M14 synthetic production-session IDOR and tenant-isolation evidence.

This gate composes the production identity adapter with representative private
business stores.  It does not claim a real PostgreSQL or production Gate.
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import timedelta
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.identity import get_current_teacher, require_local_legacy_access
from app.main import app
from app.modules.account_identity import (
    AccountLogin,
    InMemoryAccountIdentity,
    PersonalAccountProvision,
)
from app.modules.account_identity.dependencies import get_account_identity
from app.modules.personal_question_library import (
    PersonalCollectionCreate,
    PersonalQuestionLibrary,
)
from app.modules.private_library import LibraryIngestCommand, PrivateLibrary
from app.modules.teacher_memory import TeacherMemory, TeacherMemoryCommand
from app.modules.teacher_memory.dependencies import get_teacher_memory
from app.routes import library as library_routes
from app.routes.personal_question_library import get_personal_question_library


_PASSWORD = "synthetic-password-1234"
_FORBIDDEN_SELECTORS = {"account_id", "tenant_id", "owner_id"}


def _dependencies(dependant: object) -> set[object]:
    dependencies = getattr(dependant, "dependencies", ())
    return {getattr(dependant, "call", None)} | {
        call for child in dependencies for call in _dependencies(child)
    }


def _routes():
    return [
        item
        for route in app.routes
        for item in (
            route.effective_route_contexts()
            if hasattr(route, "effective_route_contexts")
            else [route]
        )
        if hasattr(item, "dependant")
    ]


def _visible_parameter_names(route: object) -> set[str]:
    dependant = route.dependant
    fields = (
        tuple(dependant.path_params)
        + tuple(dependant.query_params)
        + tuple(dependant.header_params)
        + tuple(dependant.cookie_params)
        + tuple(dependant.body_params)
    )
    names = {field.name for field in fields}
    for field in dependant.body_params:
        annotation = getattr(field, "type_", None)
        names.update(getattr(annotation, "model_fields", {}).keys())
    return names


@pytest.fixture
def production_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    identity = InMemoryAccountIdentity(session_ttl=timedelta(hours=1))
    identities = {}
    for label in ("alpha", "beta"):
        identities[label] = identity.provision_personal_account(
            PersonalAccountProvision(
                email=f"{label}@example.test",
                password=_PASSWORD,
                display_label=f"{label.title()} 教师",
                owner_id=f"owner-{label}",
            )
        )

    settings = Settings(
        production_identity_enabled=True,
        production_self_registration_enabled=False,
        beta_access_enabled=False,
        production_session_cookie_name="m14_isolation_session",
        production_session_secure_cookie=False,
        production_identity_db=tmp_path / "unused-identity.sqlite3",
        production_login_security_db=tmp_path / "login-security.sqlite3",
        production_login_security_secret="m14-isolation-secret-at-least-32-bytes",
    )
    memory = TeacherMemory(database_path=tmp_path / "memory.sqlite3")
    private_library = PrivateLibrary(
        tmp_path / "library.sqlite3",
        tmp_path / "library-files",
    )
    personal_library = PersonalQuestionLibrary(tmp_path / "personal.sqlite3")
    monkeypatch.setitem(app.dependency_overrides, get_settings, lambda: settings)
    monkeypatch.setitem(app.dependency_overrides, get_account_identity, lambda: identity)
    monkeypatch.setitem(app.dependency_overrides, get_teacher_memory, lambda: memory)
    monkeypatch.setattr(library_routes, "get_private_library", lambda: private_library)
    monkeypatch.setitem(
        app.dependency_overrides,
        get_personal_question_library,
        lambda: personal_library,
    )

    with ExitStack() as stack:
        clients = {
            label: stack.enter_context(TestClient(app))
            for label in ("alpha", "beta", "anonymous")
        }
        for label in ("alpha", "beta"):
            response = clients[label].post(
                "/api/v1/account-session",
                json={"email": f"{label}@example.test", "password": _PASSWORD},
            )
            assert response.status_code == 200
        yield clients, identities, memory, private_library, personal_library


def test_current_workbench_routes_do_not_expose_identity_selectors() -> None:
    inspected = 0
    for route in _routes():
        calls = _dependencies(route.dependant)
        if get_current_teacher not in calls or require_local_legacy_access in calls:
            continue
        inspected += 1
        assert not (_visible_parameter_names(route) & _FORBIDDEN_SELECTORS), (
            route.path,
            _visible_parameter_names(route) & _FORBIDDEN_SELECTORS,
        )
    assert inspected >= 100


def test_production_cookies_bind_private_memory_without_internal_ids(
    production_isolation,
) -> None:
    clients, identities, memory, *_ = production_isolation
    for label, grade in (("alpha", "高一"), ("beta", "高三")):
        memory.apply(
            TeacherMemoryCommand(operation="upsert", key="default_grade", value=grade),
            owner_id=identities[label].owner_id,
        )

    alpha = clients["alpha"].get(
        "/api/v1/teacher-memory/profile",
        params={"owner_id": identities["beta"].owner_id},
    )
    beta = clients["beta"].get("/api/v1/teacher-memory/profile")

    assert alpha.status_code == beta.status_code == 200
    assert alpha.json()["preferences"][0]["value"] == "高一"
    assert beta.json()["preferences"][0]["value"] == "高三"
    combined = alpha.text + beta.text
    for identity in identities.values():
        assert identity.account_id not in combined
        assert identity.tenant_id not in combined
        assert identity.owner_id not in combined
    assert clients["anonymous"].get(
        "/api/v1/teacher-memory/profile"
    ).status_code == 401


def test_known_private_object_ids_and_lists_fail_closed_across_accounts(
    production_isolation,
) -> None:
    clients, identities, _, private_library, personal_library = production_isolation
    document = Document()
    document.add_paragraph("合成函数资料：已知 f(x)=x，求 f(1)。")
    output = BytesIO()
    document.save(output)
    item = private_library.ingest(
        LibraryIngestCommand(
            title="合成函数资料",
            owner_id=identities["alpha"].owner_id,
            rights_basis="original",
            rights_acknowledged=True,
            rights_statement="合成测试资料",
        ),
        filename="synthetic.docx",
        content=output.getvalue(),
    )
    collection = personal_library.create_collection(
        PersonalCollectionCreate(name="合成私题分类"),
        owner_id=identities["alpha"].owner_id,
    )

    assert clients["alpha"].get(f"/api/v1/library/{item.library_item_id}").status_code == 200
    assert clients["beta"].get(f"/api/v1/library/{item.library_item_id}").status_code == 404
    assert clients["beta"].get("/api/v1/library").json()["total"] == 0
    assert clients["alpha"].get(
        f"/api/v1/personal-question-library/collections/{collection.collection_id}"
    ).status_code == 200
    assert clients["beta"].get(
        f"/api/v1/personal-question-library/collections/{collection.collection_id}"
    ).status_code == 404
    assert clients["beta"].get(
        "/api/v1/personal-question-library/collections"
    ).json() == {"items": [], "total": 0}


def test_identity_forgery_is_rejected_before_private_storage_changes(
    production_isolation,
) -> None:
    clients, identities, _, _, personal_library = production_isolation
    forged = clients["alpha"].post(
        "/api/v1/personal-question-library/collections",
        json={"name": "伪造归属", "owner_id": identities["beta"].owner_id},
    )

    assert forged.status_code == 422
    assert personal_library.list_collections(
        owner_id=identities["alpha"].owner_id
    ).total == 0
    assert personal_library.list_collections(
        owner_id=identities["beta"].owner_id
    ).total == 0
