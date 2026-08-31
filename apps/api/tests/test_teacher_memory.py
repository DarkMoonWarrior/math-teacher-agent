from pathlib import Path

from fastapi.testclient import TestClient

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.teacher_memory import (
    TeacherMemory,
    TeacherMemoryCommand,
    TeacherMemoryConflict,
    TeacherMemoryError,
)
from app.modules.teacher_memory.dependencies import get_teacher_memory


def teacher(teacher_id: str):
    return lambda: CurrentTeacher(
        teacher_id=teacher_id,
        source="authenticated_session",
    )


def test_teacher_memory_explicit_preferences_are_private_and_reversible(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")

    empty = memory.profile(owner_id="teacher-a")
    assert empty.version == 0
    assert empty.auto_learning_enabled is False
    assert empty.preferences == []

    saved = memory.apply(
        TeacherMemoryCommand(
            operation="upsert",
            key="default_difficulty",
            value=4,
            expected_version=0,
        ),
        owner_id="teacher-a",
    )
    assert saved.version == 1
    assert saved.preferences[0].value == 4
    assert saved.preferences[0].source.kind == "teacher_explicit"
    assert saved.preferences[0].source.confidence == 1.0
    assert memory.profile(owner_id="teacher-b").preferences == []

    enabled = memory.apply(
        TeacherMemoryCommand(
            operation="set_auto_learning",
            enabled=True,
            expected_version=1,
        ),
        owner_id="teacher-a",
    )
    assert enabled.auto_learning_enabled is True
    assert enabled.version == 2

    removed = memory.apply(
        TeacherMemoryCommand(
            operation="remove",
            key="default_difficulty",
            expected_version=2,
        ),
        owner_id="teacher-a",
    )
    assert removed.preferences == []
    assert removed.version == 3


def test_teacher_memory_rejects_arbitrary_values_and_stale_changes(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")

    try:
        memory.apply(
            TeacherMemoryCommand(
                operation="upsert",
                key="default_lesson_minutes",
                value=500,
            ),
            owner_id="teacher-a",
        )
    except TeacherMemoryError as exc:
        assert "300" in str(exc)
    else:
        raise AssertionError("invalid preference was accepted")

    memory.apply(
        TeacherMemoryCommand(operation="upsert", key="default_grade", value="高二"),
        owner_id="teacher-a",
    )
    try:
        memory.apply(
            TeacherMemoryCommand(
                operation="upsert",
                key="default_grade",
                value="高三",
                expected_version=0,
            ),
            owner_id="teacher-a",
        )
    except TeacherMemoryConflict:
        pass
    else:
        raise AssertionError("stale mutation was accepted")


def test_teacher_memory_http_identity_is_server_owned(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    app.dependency_overrides[get_teacher_memory] = lambda: memory
    app.dependency_overrides[get_current_teacher] = teacher("teacher-a")
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/teacher-memory/profile",
                json={
                    "operation": "upsert",
                    "key": "solution_detail_level",
                    "value": "detailed",
                    "expected_version": 0,
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert "owner_id" not in payload
            assert payload["preferences"][0]["source"] == {
                "kind": "teacher_explicit",
                "label": "教师明确设置",
                "confidence": 1.0,
            }

            app.dependency_overrides[get_current_teacher] = teacher("teacher-b")
            other = client.get("/api/v1/teacher-memory/profile")
            assert other.status_code == 200
            assert other.json()["preferences"] == []
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_teacher_memory, None)


def test_owner_preferences_only_fill_missing_blueprint_fields(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    for key, value in (
        ("default_grade", "高三"),
        ("default_lesson_minutes", 50),
        ("default_difficulty", 5),
    ):
        memory.apply(
            TeacherMemoryCommand(operation="upsert", key=key, value=value),
            owner_id="teacher-a",
        )

    app.dependency_overrides[get_teacher_memory] = lambda: memory
    app.dependency_overrides[get_current_teacher] = teacher("teacher-a")
    try:
        with TestClient(app) as client:
            lesson = client.post(
                "/api/v1/lesson-plans/blueprints/plan",
                json={"brief": "设计一节函数单调性专题复习课"},
            )
            assert lesson.status_code == 200
            assert lesson.json()["grade_scope"] == "高三"
            assert lesson.json()["duration_minutes"] == 50
            assert [item["key"] for item in lesson.json()["applied_preferences"]] == [
                "default_grade",
                "default_lesson_minutes",
            ]

            paper = client.post(
                "/api/v1/exam-papers/blueprints/plan",
                json={"brief": "组一份函数阶段检测"},
            )
            assert paper.status_code == 200
            assert paper.json()["grade_scope"] == "高三"
            assert paper.json()["difficulty_profile"] == "challenge"
            assert [item["key"] for item in paper.json()["applied_preferences"]] == [
                "default_grade",
                "default_difficulty",
            ]

            app.dependency_overrides[get_current_teacher] = teacher("teacher-b")
            other = client.post(
                "/api/v1/exam-papers/blueprints/plan",
                json={"brief": "组一份函数阶段检测"},
            )
            assert other.status_code == 200
            assert other.json()["grade_scope"] == "高中通用"
            assert other.json()["difficulty_profile"] == "balanced"
            assert other.json()["applied_preferences"] == []
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_teacher_memory, None)
