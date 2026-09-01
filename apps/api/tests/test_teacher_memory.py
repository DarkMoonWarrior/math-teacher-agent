from pathlib import Path

from fastapi.testclient import TestClient

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.teacher_memory import (
    TeacherMemory,
    TeacherMemoryCommand,
    TeacherMemoryConflict,
    TeacherMemoryError,
    TeacherPreferenceSignal,
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

            forged_signal = client.post(
                "/api/v1/teacher-memory/profile",
                json={
                    "operation": "observe",
                    "key": "default_grade",
                    "value": "高三",
                    "evidence_category": "confirmed_lesson_version",
                    "evidence_id": "browser-forged",
                },
            )
            assert forged_signal.status_code == 422

            memory.apply(
                TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
                owner_id="teacher-a",
            )
            proposal_profile = memory.profile(owner_id="teacher-a")
            for index in range(3):
                proposal_profile = memory.apply(
                    TeacherPreferenceSignal(
                        key="default_grade",
                        value="高二",
                        evidence_category="confirmed_lesson_version",
                        evidence_id=f"lesson:http:{index}",
                    ),
                    owner_id="teacher-a",
                )
            proposal_id = proposal_profile.proposals[0].proposal_id

            app.dependency_overrides[get_current_teacher] = teacher("teacher-b")
            cross_owner_review = client.post(
                "/api/v1/teacher-memory/profile",
                json={
                    "operation": "accept_proposal",
                    "proposal_id": proposal_id,
                    "expected_version": 0,
                },
            )
            assert cross_owner_review.status_code == 422
            other = client.get("/api/v1/teacher-memory/profile")
            assert other.status_code == 200
            assert other.json()["preferences"] == []

            app.dependency_overrides[get_current_teacher] = teacher("teacher-a")
            accepted = client.post(
                "/api/v1/teacher-memory/profile",
                json={
                    "operation": "accept_proposal",
                    "proposal_id": proposal_id,
                    "expected_version": proposal_profile.version,
                },
            )
            assert accepted.status_code == 200
            assert any(
                item["key"] == "default_grade" and item["value"] == "高二"
                for item in accepted.json()["preferences"]
            )
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


def test_teacher_memory_only_proposes_repeated_structured_signals_when_enabled(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    signal = lambda evidence_id: TeacherPreferenceSignal(
        key="default_lesson_minutes",
        value=45,
        evidence_category="confirmed_lesson_version",
        evidence_id=evidence_id,
    )

    memory.apply(signal("lesson:off:1"), owner_id="teacher-a")
    assert memory.profile(owner_id="teacher-a").proposals == []

    memory.apply(
        TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
        owner_id="teacher-a",
    )
    memory.apply(signal("lesson:1"), owner_id="teacher-a")
    memory.apply(signal("lesson:2"), owner_id="teacher-a")
    assert memory.profile(owner_id="teacher-a").proposals == []

    proposed = memory.apply(signal("lesson:3"), owner_id="teacher-a")
    assert len(proposed.proposals) == 1
    proposal = proposed.proposals[0]
    assert proposal.key == "default_lesson_minutes"
    assert proposal.value == 45
    assert proposal.status == "pending_teacher_review"
    assert proposal.evidence.category == "confirmed_lesson_version"
    assert proposal.evidence.occurrence_count == 3
    assert 0.5 < proposal.confidence < 1.0
    assert proposed.preferences == []
    assert memory.planning_defaults(owner_id="teacher-a").preferences == []
    assert memory.profile(owner_id="teacher-b").proposals == []
    duplicate = memory.apply(signal("lesson:3"), owner_id="teacher-a")
    assert duplicate.proposals[0].evidence.occurrence_count == 3


def test_explicit_preference_removes_same_key_proposal_without_auto_promoting_it(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    memory.apply(
        TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
        owner_id="teacher-a",
    )
    for index in range(3):
        memory.apply(
            TeacherPreferenceSignal(
                key="default_grade",
                value="高二",
                evidence_category="confirmed_paper_version",
                evidence_id=f"paper:{index}",
            ),
            owner_id="teacher-a",
        )
    assert memory.profile(owner_id="teacher-a").preferences == []
    assert len(memory.profile(owner_id="teacher-a").proposals) == 1

    explicit = memory.apply(
        TeacherMemoryCommand(operation="upsert", key="default_grade", value="高三"),
        owner_id="teacher-a",
    )
    assert explicit.proposals == []
    assert explicit.preferences[0].value == "高三"
    assert explicit.preferences[0].source.kind == "teacher_explicit"


def test_teacher_can_accept_a_proposal_as_an_explicit_preference(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    enabled = memory.apply(
        TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
        owner_id="teacher-a",
    )
    profile = enabled
    for index in range(3):
        profile = memory.apply(
            TeacherPreferenceSignal(
                key="default_lesson_minutes",
                value=45,
                evidence_category="confirmed_lesson_version",
                evidence_id=f"lesson:accept:{index}",
            ),
            owner_id="teacher-a",
        )

    proposal = profile.proposals[0]
    accepted = memory.apply(
        TeacherMemoryCommand(
            operation="accept_proposal",
            proposal_id=proposal.proposal_id,
            expected_version=profile.version,
        ),
        owner_id="teacher-a",
    )

    assert accepted.proposals == []
    assert accepted.preferences[0].key == "default_lesson_minutes"
    assert accepted.preferences[0].value == 45
    assert accepted.preferences[0].source.kind == "teacher_explicit"
    assert accepted.preferences[0].source.confidence == 1.0
    assert memory.planning_defaults(owner_id="teacher-a").preferences[0].value == 45
    assert memory.profile(owner_id="teacher-b").preferences == []

    try:
        memory.apply(
            TeacherMemoryCommand(
                operation="accept_proposal",
                proposal_id=proposal.proposal_id,
            ),
            owner_id="teacher-b",
        )
    except TeacherMemoryError as exc:
        assert "提议" in str(exc)
    else:
        raise AssertionError("another owner accepted a private proposal")


def test_rejected_proposal_needs_three_new_distinct_signals_before_relearning(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    memory.apply(
        TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
        owner_id="teacher-a",
    )

    def observe(index: int):
        return memory.apply(
            TeacherPreferenceSignal(
                key="default_difficulty",
                value=4,
                evidence_category="confirmed_paper_version",
                evidence_id=f"paper:reject:{index}",
            ),
            owner_id="teacher-a",
        )

    profile = observe(1)
    profile = observe(2)
    profile = observe(3)
    proposal = profile.proposals[0]
    rejected = memory.apply(
        TeacherMemoryCommand(
            operation="reject_proposal",
            proposal_id=proposal.proposal_id,
            expected_version=profile.version,
        ),
        owner_id="teacher-a",
    )
    assert rejected.proposals == []
    assert rejected.preferences == []

    assert observe(4).proposals == []
    assert observe(4).proposals == []  # duplicate evidence is not a new signal
    assert observe(5).proposals == []
    relearned = observe(6)
    assert len(relearned.proposals) == 1
    assert relearned.proposals[0].value == 4
    assert relearned.proposals[0].evidence.occurrence_count == 6


def test_teacher_can_correct_a_proposal_before_accepting_it(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    memory.apply(
        TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
        owner_id="teacher-a",
    )
    profile = memory.profile(owner_id="teacher-a")
    for index in range(3):
        profile = memory.apply(
            TeacherPreferenceSignal(
                key="default_grade",
                value="高二",
                evidence_category="confirmed_paper_version",
                evidence_id=f"paper:correct:{index}",
            ),
            owner_id="teacher-a",
        )

    proposal = profile.proposals[0]
    corrected = memory.apply(
        TeacherMemoryCommand(
            operation="correct_proposal",
            proposal_id=proposal.proposal_id,
            value="高三",
            expected_version=profile.version,
        ),
        owner_id="teacher-a",
    )

    assert corrected.proposals == []
    assert corrected.preferences[0].key == "default_grade"
    assert corrected.preferences[0].value == "高三"
    assert corrected.preferences[0].source.kind == "teacher_explicit"
    assert memory.planning_defaults(owner_id="teacher-a").preferences[0].value == "高三"


def test_teacher_memory_profile_exposes_structured_feedback_and_retention_policy(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    memory.apply(
        TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
        owner_id="teacher-a",
    )
    profile = memory.profile(owner_id="teacher-a")
    for index in range(3):
        profile = memory.apply(
            TeacherPreferenceSignal(
                key="default_difficulty",
                value=4,
                evidence_category="confirmed_paper_version",
                evidence_id=f"paper:feedback:{index}",
            ),
            owner_id="teacher-a",
        )
    proposal = profile.proposals[0]
    rejected = memory.apply(
        TeacherMemoryCommand(
            operation="reject_proposal",
            proposal_id=proposal.proposal_id,
            expected_version=profile.version,
        ),
        owner_id="teacher-a",
    )

    assert "删除全部教师记忆" in rejected.retention_note
    assert len(rejected.feedback) == 1
    feedback = rejected.feedback[0]
    assert feedback.key == "default_difficulty"
    assert feedback.proposed_value == 4
    assert feedback.resolved_value is None
    assert feedback.action == "reject"
    assert feedback.evidence.category == "confirmed_paper_version"
    assert feedback.evidence.occurrence_count == 3
    assert not hasattr(feedback, "owner_id")
    assert not hasattr(feedback, "evidence_id")
    assert memory.profile(owner_id="teacher-b").feedback == []


def test_delete_all_teacher_memory_requires_confirmation_and_preserves_version_order(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    memory.apply(
        TeacherMemoryCommand(
            operation="upsert",
            key="default_grade",
            value="高二",
        ),
        owner_id="teacher-a",
    )
    memory.apply(
        TeacherMemoryCommand(
            operation="upsert",
            key="default_grade",
            value="高三",
        ),
        owner_id="teacher-b",
    )
    before = memory.profile(owner_id="teacher-a")

    try:
        memory.apply(
            TeacherMemoryCommand(
                operation="delete_all",
                confirmation="删除",
                expected_version=before.version,
            ),
            owner_id="teacher-a",
        )
    except TeacherMemoryError as exc:
        assert "删除全部教师记忆" in str(exc)
    else:
        raise AssertionError("teacher memory was deleted without fixed confirmation")

    deleted = memory.apply(
        TeacherMemoryCommand(
            operation="delete_all",
            confirmation="删除全部教师记忆",
            expected_version=before.version,
        ),
        owner_id="teacher-a",
    )
    assert deleted.version == before.version + 1
    assert deleted.auto_learning_enabled is False
    assert deleted.preferences == []
    assert deleted.proposals == []
    assert deleted.feedback == []
    assert memory.planning_defaults(owner_id="teacher-a").preferences == []
    assert memory.profile(owner_id="teacher-b").preferences[0].value == "高三"

    try:
        memory.apply(
            TeacherMemoryCommand(
                operation="upsert",
                key="default_grade",
                value="高一",
                expected_version=before.version,
            ),
            owner_id="teacher-a",
        )
    except TeacherMemoryConflict:
        pass
    else:
        raise AssertionError("a stale page overwrote the post-deletion profile")


def test_teacher_memory_http_export_and_delete_are_owner_scoped(tmp_path: Path) -> None:
    memory = TeacherMemory(database_path=tmp_path / "teacher-memory.sqlite3")
    saved = memory.apply(
        TeacherMemoryCommand(operation="upsert", key="default_grade", value="高二"),
        owner_id="teacher-a",
    )
    memory.apply(
        TeacherMemoryCommand(operation="upsert", key="default_grade", value="高三"),
        owner_id="teacher-b",
    )
    app.dependency_overrides[get_teacher_memory] = lambda: memory
    app.dependency_overrides[get_current_teacher] = teacher("teacher-a")
    try:
        with TestClient(app) as client:
            exported = client.get("/api/v1/teacher-memory/export")
            assert exported.status_code == 200
            assert exported.headers["content-type"].startswith("application/json")
            assert "attachment" in exported.headers["content-disposition"]
            payload = exported.json()
            assert payload["preferences"][0]["value"] == "高二"
            assert "owner_id" not in payload

            deleted = client.post(
                "/api/v1/teacher-memory/profile",
                json={
                    "operation": "delete_all",
                    "confirmation": "删除全部教师记忆",
                    "expected_version": saved.version,
                },
            )
            assert deleted.status_code == 200
            assert deleted.json()["preferences"] == []

            app.dependency_overrides[get_current_teacher] = teacher("teacher-b")
            other = client.get("/api/v1/teacher-memory/export")
            assert other.status_code == 200
            assert other.json()["preferences"][0]["value"] == "高三"
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_teacher_memory, None)
