from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

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


_ROOT = Path(__file__).resolve().parents[3]
_CASES = _ROOT / "data" / "test-fixtures" / "teacher-memory" / "eval-cases.json"


def _teacher(teacher_id: str):
    return lambda: CurrentTeacher(teacher_id=teacher_id, source="authenticated_session")


def _expect_error(violations: dict[str, int], key: str, expected, operation) -> None:
    try:
        operation()
    except expected:
        return
    except Exception:
        violations["unexpected_outcome"] += 1
        return
    violations[key] += 1


def _propose(
    memory: TeacherMemory,
    *,
    owner_id: str,
    key: str,
    value: str | int,
    category: str,
    prefix: str,
):
    profile = memory.profile(owner_id=owner_id)
    for index in range(1, 4):
        profile = memory.apply(
            TeacherPreferenceSignal(
                key=key,
                value=value,
                evidence_category=category,
                evidence_id=f"{prefix}:{index}",
            ),
            owner_id=owner_id,
        )
    return profile


def test_teacher_memory_fixed_synthetic_evaluation(tmp_path: Path) -> None:
    fixture = json.loads(_CASES.read_text(encoding="utf-8"))
    case_ids = {case["id"] for case in fixture["cases"]}
    assert fixture["evaluation_id"] == "teacher-memory-synthetic-v1"
    assert fixture["source"] == "project-authored-synthetic"
    assert fixture["synthetic"] is True
    assert len(case_ids) == len(fixture["cases"]) == 26

    violations = {
        "unexpected_outcome": 0,
        "invalid_preference_accepted": 0,
        "cross_owner_leak": 0,
        "stale_write_accepted": 0,
        "planning_default_drift": 0,
        "silent_inference": 0,
        "proposal_threshold_bypass": 0,
        "duplicate_signal_counted": 0,
        "feedback_drift": 0,
        "retention_bypass": 0,
        "private_content_exposed": 0,
        "agent_privilege_escalation": 0,
    }
    executed: set[str] = set()

    memory = TeacherMemory(database_path=tmp_path / "explicit.sqlite3")
    saved = memory.apply(
        TeacherMemoryCommand(operation="upsert", key="default_grade", value="高二"),
        owner_id="teacher-a",
    )
    if (
        saved.preferences[0].value != "高二"
        or saved.preferences[0].source.kind != "teacher_explicit"
        or saved.preferences[0].source.confidence != 1.0
    ):
        violations["unexpected_outcome"] += 1
    executed.add("explicit_allowlist")

    _expect_error(
        violations,
        "invalid_preference_accepted",
        TeacherMemoryError,
        lambda: memory.apply(
            TeacherMemoryCommand(operation="upsert", key="default_difficulty", value=9),
            owner_id="teacher-a",
        ),
    )
    executed.add("invalid_value_rejected")
    if memory.profile(owner_id="teacher-b").preferences:
        violations["cross_owner_leak"] += 1
    executed.add("owner_profile_isolated")
    _expect_error(
        violations,
        "stale_write_accepted",
        TeacherMemoryConflict,
        lambda: memory.apply(
            TeacherMemoryCommand(
                operation="upsert", key="default_grade", value="高三", expected_version=0
            ),
            owner_id="teacher-a",
        ),
    )
    executed.add("stale_version_rejected")

    defaults = memory.planning_defaults(owner_id="teacher-a")
    defaults_json = defaults.model_dump_json()
    if (
        defaults.get("default_grade") is None
        or "owner" in defaults_json
        or any(token in defaults_json for token in ("brief", "stem", "solution", "lesson_body"))
    ):
        violations["planning_default_drift"] += 1
    executed.add("planning_defaults_structured_only")

    app.dependency_overrides[get_teacher_memory] = lambda: memory
    app.dependency_overrides[get_current_teacher] = _teacher("teacher-a")
    try:
        with TestClient(app) as client:
            lesson = client.post(
                "/api/v1/lesson-plans/blueprints/plan",
                json={"brief": "为高三函数复习准备一节 50 分钟教案"},
            )
            if (
                lesson.status_code != 200
                or lesson.json()["grade_scope"] != "高三"
                or any(
                    item["key"] == "default_grade"
                    for item in lesson.json()["applied_preferences"]
                )
            ):
                violations["planning_default_drift"] += 1
            executed.add("lesson_explicit_field_wins")

            paper = client.post(
                "/api/v1/exam-papers/blueprints/plan",
                json={"brief": "组一份函数阶段检测"},
            )
            if (
                paper.status_code != 200
                or paper.json()["grade_scope"] != "高二"
                or not any(
                    item["key"] == "default_grade"
                    for item in paper.json()["applied_preferences"]
                )
            ):
                violations["planning_default_drift"] += 1
            executed.add("paper_missing_fields_use_defaults")

            forged = client.post(
                "/api/v1/teacher-memory/profile",
                json={
                    "operation": "upsert",
                    "key": "default_grade",
                    "value": "高一",
                    "owner_id": "teacher-b",
                    "evidence_id": "browser-content",
                },
            )
            if forged.status_code != 422:
                violations["cross_owner_leak"] += 1
            executed.add("http_owner_spoof_rejected")
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_teacher_memory, None)

    inference = TeacherMemory(database_path=tmp_path / "inference.sqlite3")
    off = inference.apply(
        TeacherPreferenceSignal(
            key="default_lesson_minutes",
            value=45,
            evidence_category="confirmed_lesson_version",
            evidence_id="lesson:off",
        ),
        owner_id="teacher-a",
    )
    if off.proposals or off.version != 0:
        violations["silent_inference"] += 1
    executed.add("auto_learning_off")
    inference.apply(
        TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
        owner_id="teacher-a",
    )
    for index in range(1, 3):
        partial = inference.apply(
            TeacherPreferenceSignal(
                key="default_lesson_minutes",
                value=45,
                evidence_category="confirmed_lesson_version",
                evidence_id=f"lesson:threshold:{index}",
            ),
            owner_id="teacher-a",
        )
    if partial.proposals:
        violations["proposal_threshold_bypass"] += 1
    proposed = inference.apply(
        TeacherPreferenceSignal(
            key="default_lesson_minutes",
            value=45,
            evidence_category="confirmed_lesson_version",
            evidence_id="lesson:threshold:3",
        ),
        owner_id="teacher-a",
    )
    if len(proposed.proposals) != 1 or proposed.proposals[0].evidence.occurrence_count != 3:
        violations["proposal_threshold_bypass"] += 1
    executed.add("proposal_threshold")
    duplicate = inference.apply(
        TeacherPreferenceSignal(
            key="default_lesson_minutes",
            value=45,
            evidence_category="confirmed_lesson_version",
            evidence_id="lesson:threshold:3",
        ),
        owner_id="teacher-a",
    )
    if duplicate.proposals[0].evidence.occurrence_count != 3:
        violations["duplicate_signal_counted"] += 1
    executed.add("duplicate_evidence_idempotent")
    if inference.planning_defaults(owner_id="teacher-a").preferences:
        violations["silent_inference"] += 1
    executed.add("proposal_never_auto_applied")
    accepted = inference.apply(
        TeacherMemoryCommand(
            operation="accept_proposal",
            proposal_id=proposed.proposals[0].proposal_id,
            expected_version=proposed.version,
        ),
        owner_id="teacher-a",
    )
    if (
        accepted.preferences[0].value != 45
        or accepted.preferences[0].source.confidence != 1.0
        or accepted.proposals
    ):
        violations["feedback_drift"] += 1
    executed.add("accept_promotes_explicit")

    feedback_memory = TeacherMemory(database_path=tmp_path / "feedback.sqlite3")
    feedback_memory.apply(
        TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
        owner_id="teacher-a",
    )
    rejection_candidate = _propose(
        feedback_memory,
        owner_id="teacher-a",
        key="default_difficulty",
        value=4,
        category="confirmed_paper_version",
        prefix="paper:reject",
    )
    rejected = feedback_memory.apply(
        TeacherMemoryCommand(
            operation="reject_proposal",
            proposal_id=rejection_candidate.proposals[0].proposal_id,
            expected_version=rejection_candidate.version,
        ),
        owner_id="teacher-a",
    )
    feedback_json = rejected.feedback[0].model_dump_json()
    if (
        rejected.feedback[0].action != "reject"
        or "evidence_id" in feedback_json
        or "owner_id" in feedback_json
    ):
        violations["feedback_drift"] += 1
    executed.add("reject_records_structured_feedback")
    for index in (4, 5):
        cooldown = feedback_memory.apply(
            TeacherPreferenceSignal(
                key="default_difficulty",
                value=4,
                evidence_category="confirmed_paper_version",
                evidence_id=f"paper:reject:{index}",
            ),
            owner_id="teacher-a",
        )
    relearned = feedback_memory.apply(
        TeacherPreferenceSignal(
            key="default_difficulty",
            value=4,
            evidence_category="confirmed_paper_version",
            evidence_id="paper:reject:6",
        ),
        owner_id="teacher-a",
    )
    if cooldown.proposals or len(relearned.proposals) != 1:
        violations["feedback_drift"] += 1
    executed.add("rejection_cooldown")

    correction_memory = TeacherMemory(database_path=tmp_path / "correction.sqlite3")
    correction_memory.apply(
        TeacherMemoryCommand(operation="set_auto_learning", enabled=True),
        owner_id="teacher-a",
    )
    correction_candidate = _propose(
        correction_memory,
        owner_id="teacher-a",
        key="default_grade",
        value="高二",
        category="confirmed_paper_version",
        prefix="paper:correct",
    )
    proposal_id = correction_candidate.proposals[0].proposal_id
    _expect_error(
        violations,
        "cross_owner_leak",
        TeacherMemoryError,
        lambda: correction_memory.apply(
            TeacherMemoryCommand(operation="accept_proposal", proposal_id=proposal_id),
            owner_id="teacher-b",
        ),
    )
    executed.add("cross_owner_proposal_review")
    corrected = correction_memory.apply(
        TeacherMemoryCommand(
            operation="correct_proposal",
            proposal_id=proposal_id,
            value="高三",
            expected_version=correction_candidate.version,
        ),
        owner_id="teacher-a",
    )
    if corrected.preferences[0].value != "高三" or corrected.feedback[0].action != "correct":
        violations["feedback_drift"] += 1
    executed.add("correct_promotes_validated")
    if correction_memory.profile(owner_id="teacher-b").feedback:
        violations["cross_owner_leak"] += 1
    executed.add("feedback_owner_isolated")
    safe_profile_json = corrected.model_dump_json()
    if any(
        token in safe_profile_json
        for token in ("owner_id", "evidence_id", "question_stem", "solution_body", "lesson_body")
    ):
        violations["private_content_exposed"] += 1
    executed.add("profile_omits_private_content")

    lifecycle = TeacherMemory(database_path=tmp_path / "lifecycle.sqlite3")
    before = lifecycle.apply(
        TeacherMemoryCommand(operation="upsert", key="default_grade", value="高一"),
        owner_id="teacher-a",
    )
    lifecycle.apply(
        TeacherMemoryCommand(operation="upsert", key="default_grade", value="高三"),
        owner_id="teacher-b",
    )
    app.dependency_overrides[get_teacher_memory] = lambda: lifecycle
    app.dependency_overrides[get_current_teacher] = _teacher("teacher-a")
    try:
        with TestClient(app) as client:
            exported = client.get("/api/v1/teacher-memory/export")
            export_payload = exported.json()
            if (
                exported.status_code != 200
                or "attachment" not in exported.headers.get("content-disposition", "")
                or export_payload["preferences"][0]["value"] != "高一"
                or "高三" in exported.text
                or "owner_id" in exported.text
            ):
                violations["cross_owner_leak"] += 1
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        app.dependency_overrides.pop(get_teacher_memory, None)
    executed.add("export_owner_scoped")

    _expect_error(
        violations,
        "retention_bypass",
        TeacherMemoryError,
        lambda: lifecycle.apply(
            TeacherMemoryCommand(
                operation="delete_all",
                confirmation="删除",
                expected_version=before.version,
            ),
            owner_id="teacher-a",
        ),
    )
    executed.add("delete_confirmation_required")
    deleted = lifecycle.apply(
        TeacherMemoryCommand(
            operation="delete_all",
            confirmation="删除全部教师记忆",
            expected_version=before.version,
        ),
        owner_id="teacher-a",
    )
    if deleted.preferences or deleted.proposals or deleted.feedback or deleted.auto_learning_enabled:
        violations["retention_bypass"] += 1
    executed.add("delete_clears_owner")
    if lifecycle.profile(owner_id="teacher-b").preferences[0].value != "高三":
        violations["cross_owner_leak"] += 1
    executed.add("delete_preserves_other_owner")
    if deleted.version != before.version + 1:
        violations["retention_bypass"] += 1
    executed.add("delete_version_monotonic")
    _expect_error(
        violations,
        "stale_write_accepted",
        TeacherMemoryConflict,
        lambda: lifecycle.apply(
            TeacherMemoryCommand(
                operation="upsert",
                key="default_grade",
                value="高二",
                expected_version=before.version,
            ),
            owner_id="teacher-a",
        ),
    )
    executed.add("stale_after_delete_rejected")

    _expect_error(
        violations,
        "cross_owner_leak",
        ValidationError,
        lambda: TeacherMemoryCommand.model_validate(
            {
                "operation": "upsert",
                "key": "default_grade",
                "value": "高二",
                "owner_id": "teacher-b",
                "raw_task": "private content",
            }
        ),
    )

    tool_source = (
        _ROOT / "apps" / "agent" / "src" / "tools" / "teacher-tools.ts"
    ).read_text(encoding="utf-8")
    allowlist_match = re.search(
        r"TEACHER_TOOL_ALLOWLIST[^=]*=\s*\[(.*?)\];", tool_source, re.DOTALL
    )
    tool_names = set(re.findall(r'"([a-z_]+)"', allowlist_match.group(1))) if allowlist_match else set()
    if any(
        token in name
        for name in tool_names
        for token in ("memory", "preference", "export", "delete", "retention")
    ):
        violations["agent_privilege_escalation"] += 1
    executed.add("agent_no_memory_mutation_tool")

    if executed != case_ids:
        violations["unexpected_outcome"] += len(case_ids.symmetric_difference(executed))
    print(f"\n[m11-eval] cases={len(case_ids)} violations={violations}")
    assert violations == {key: 0 for key in violations}, violations
