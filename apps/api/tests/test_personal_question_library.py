from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.personal_question_library import (
    PersonalCategoryCreate,
    PersonalCategoryUpdate,
    PersonalCollectionCreate,
    PersonalCollectionUpdate,
    PersonalQuestionLibrary,
    PersonalQuestionLibraryConflict,
)
from app.routes.personal_question_library import get_personal_question_library


def make_library(tmp_path: Path) -> PersonalQuestionLibrary:
    return PersonalQuestionLibrary(tmp_path / "personal-question-library.sqlite3")


def teacher(teacher_id: str):
    def dependency() -> CurrentTeacher:
        return CurrentTeacher(
            teacher_id=teacher_id,
            source="authenticated_session",
        )

    return dependency


def test_collections_are_owner_only_and_never_expose_owner_or_public_transitions(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    mine = library.create_collection(
        PersonalCollectionCreate(name="  高二 圆锥曲线  ", description="月考备用题"),
        owner_id="teacher_a",
    )
    other = library.create_collection(
        PersonalCollectionCreate(name="高二 圆锥曲线"),
        owner_id="teacher_b",
    )

    assert mine.collection_id != other.collection_id
    assert mine.name == "高二 圆锥曲线"
    assert library.list_collections(owner_id="teacher_a").total == 1
    assert (
        library.list_collections(owner_id="teacher_b").items[0].collection_id
        == other.collection_id
    )
    with pytest.raises(KeyError):
        library.get_collection(mine.collection_id, owner_id="teacher_b")

    payload = mine.model_dump(mode="json")
    assert payload["visibility"] == "owner_only"
    assert payload["public_search_allowed"] is False
    assert payload["share_allowed"] is False
    assert payload["commercial_use_allowed"] is False
    assert payload["model_training_allowed"] is False
    assert "owner_id" not in payload
    assert "publish" not in str(payload).lower()


def test_collection_names_are_unique_per_owner_and_can_be_renamed(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    first = library.create_collection(
        PersonalCollectionCreate(name="函数专题"),
        owner_id="teacher_a",
    )
    with pytest.raises(PersonalQuestionLibraryConflict, match="同名"):
        library.create_collection(
            PersonalCollectionCreate(name="  函数专题  "),
            owner_id="teacher_a",
        )

    updated = library.update_collection(
        first.collection_id,
        PersonalCollectionUpdate(name="导数专题", description="一轮复习"),
        owner_id="teacher_a",
    )
    assert updated.name == "导数专题"
    assert updated.description == "一轮复习"


def test_categories_are_scoped_to_owner_and_collection(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    mine = library.create_collection(
        PersonalCollectionCreate(name="我的私题"),
        owner_id="teacher_a",
    )
    category = library.create_category(
        mine.collection_id,
        PersonalCategoryCreate(name="易错题", description="课堂诊断", sort_order=20),
        owner_id="teacher_a",
    )

    assert library.get_collection(mine.collection_id, owner_id="teacher_a").category_count == 1
    assert library.list_categories(mine.collection_id, owner_id="teacher_a").items == [category]
    with pytest.raises(KeyError):
        library.list_categories(mine.collection_id, owner_id="teacher_b")
    with pytest.raises(KeyError):
        library.get_category(category.category_id, owner_id="teacher_b")
    with pytest.raises(KeyError):
        library.update_category(
            category.category_id,
            PersonalCategoryUpdate(name="越权分类"),
            owner_id="teacher_b",
        )

    updated = library.update_category(
        category.category_id,
        PersonalCategoryUpdate(name="压轴题", sort_order=5),
        owner_id="teacher_a",
    )
    assert updated.name == "压轴题"
    assert updated.description == "课堂诊断"
    assert updated.sort_order == 5


def test_storage_namespace_has_no_publication_or_question_bank_tables(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    with sqlite3.connect(library.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        columns = {
            row[1]
            for table in tables
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }

    assert tables == {
        "personal_question_collections",
        "personal_question_categories",
    }
    assert "visibility" not in columns
    assert "publish_status" not in columns
    assert "share_status" not in columns
    assert "commercial_status" not in columns


def test_http_identity_binding_rejects_owner_selection_and_cross_owner_access(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    app.dependency_overrides[get_personal_question_library] = lambda: library
    app.dependency_overrides[get_current_teacher] = teacher("teacher_a")
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/personal-question-library/collections",
                json={"name": "解析几何", "description": "个人整理"},
            )
            assert created.status_code == 201
            collection = created.json()
            assert "owner_id" not in collection

            forged = client.post(
                "/api/v1/personal-question-library/collections",
                json={"name": "伪造归属", "owner_id": "teacher_b"},
            )
            assert forged.status_code == 422

            category = client.post(
                "/api/v1/personal-question-library/collections/"
                f"{collection['collection_id']}/categories",
                json={"name": "课堂例题", "sort_order": 1},
            )
            assert category.status_code == 201
            category_id = category.json()["category_id"]

            app.dependency_overrides[get_current_teacher] = teacher("teacher_b")
            assert client.get(
                f"/api/v1/personal-question-library/collections/{collection['collection_id']}"
            ).status_code == 404
            assert client.get(
                f"/api/v1/personal-question-library/categories/{category_id}"
            ).status_code == 404
            assert client.get(
                "/api/v1/personal-question-library/collections"
            ).json() == {"items": [], "total": 0}
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_personal_question_library, None)


def test_public_routes_have_no_publish_share_admin_or_delete_interface() -> None:
    personal_paths = {
        path: operations
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/personal-question-library")
    }
    serialized = str(personal_paths).lower()

    assert personal_paths
    methods = {
        method for operations in personal_paths.values() for method in operations
    }
    assert "delete" not in methods
    assert "publish" not in serialized
    assert "share" not in serialized
    assert "admin" not in serialized
