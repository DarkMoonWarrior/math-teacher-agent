from __future__ import annotations

import json
import re
from pathlib import Path
from zipfile import ZipFile

from pydantic import ValidationError

from app.modules.lesson_exports import SavedLessonPlanDocumentRenderer
from app.modules.lesson_plans import (
    LessonBlockEditing,
    LessonBlockEditingConflict,
    LessonBlockRewriteCommand,
    LessonBlueprintBrief,
    LessonBlueprintPlanning,
    LessonBlueprintPlanningError,
    LessonDraftCommand,
    LessonDrafting,
    LessonDraftingConflict,
    LessonDraftingError,
    LessonSavedExporting,
    LessonSavedExportingError,
    LessonVersionLifecycleCommand,
    LessonVersionSaveCommand,
    LessonVersioning,
)
from apps.api.tests.test_lesson_blueprint_planning import _catalog
from apps.api.tests.test_lesson_drafting import (
    _SourceSelection,
    _complete_lesson_draft,
    _source_draft,
)


_ROOT = Path(__file__).resolve().parents[3]
_CASES = _ROOT / "data" / "test-fixtures" / "lesson-agent" / "eval-cases.json"
_V2_MARKER = "M10-ONLY-IN-VERSION-TWO"


def _record_raise(
    violations: dict[str, int],
    key: str,
    expected: type[BaseException],
    operation,
) -> None:
    try:
        operation()
    except expected:
        return
    except Exception:
        violations["unexpected_outcome"] += 1
        return
    violations[key] += 1


def test_lesson_agent_fixed_synthetic_evaluation(tmp_path: Path) -> None:
    fixture = json.loads(_CASES.read_text(encoding="utf-8"))
    case_ids = {case["id"] for case in fixture["cases"]}
    assert fixture["evaluation_id"] == "lesson-agent-synthetic-v1"
    assert fixture["source"] == "project-authored-synthetic"
    assert fixture["synthetic"] is True
    assert len(case_ids) == len(fixture["cases"]) == 28

    violations = {
        "unexpected_outcome": 0,
        "scope_escape": 0,
        "source_gate_bypass": 0,
        "cross_owner_leak": 0,
        "incomplete_lesson_delivered": 0,
        "question_completeness_lost": 0,
        "alignment_broken": 0,
        "source_traceability_lost": 0,
        "targeted_edit_drift": 0,
        "locked_edit_bypass": 0,
        "question_fact_drift": 0,
        "implicit_save": 0,
        "immutable_version_drift": 0,
        "export_snapshot_drift": 0,
        "agent_privilege_escalation": 0,
    }
    executed: set[str] = set()

    planning = LessonBlueprintPlanning(curriculum_catalog=_catalog())
    blueprint = planning.plan(
        LessonBlueprintBrief(
            brief="为高一函数单调性准备一份 45 分钟新授课教案，学生基础中等，安排 4 道练习"
        )
    )
    if (
        blueprint.status != "lesson_blueprint_draft"
        or not blueprint.editable
        or blueprint.confirmed
        or blueprint.saved
        or blueprint.side_effects
    ):
        violations["unexpected_outcome"] += 1
    executed.add("grounded_editable_blueprint")

    defaulted = planning.plan(LessonBlueprintBrief(brief="设计一节函数单调性专题复习课"))
    if not defaulted.assumptions or not all(
        any(label in item for item in defaulted.assumptions)
        for label in ("年级", "课时", "学情", "例题与练习数量")
    ):
        violations["unexpected_outcome"] += 1
    executed.add("visible_blueprint_defaults")

    _record_raise(
        violations,
        "scope_escape",
        LessonBlueprintPlanningError,
        lambda: planning.plan(LessonBlueprintBrief(brief="设计一节本科数学分析与傅里叶分析课程")),
    )
    executed.add("university_scope_rejected")

    source = _source_draft()
    if not source.selection_complete or source.gaps or source.saved or source.side_effects:
        violations["source_gate_bypass"] += 1
    executed.add("confirmed_source_selection")
    if (
        not source.private_resources
        or any(item.owner_scope != "current_owner_only" for item in source.private_resources)
    ):
        violations["cross_owner_leak"] += 1
    executed.add("private_source_owner_scope")

    incomplete = _source_draft(complete=False)
    if incomplete.selection_complete or not incomplete.gaps or incomplete.questions:
        violations["source_gate_bypass"] += 1
    executed.add("truthful_source_gap")

    drafting, draft = _complete_lesson_draft()
    if (
        not draft.objectives
        or not draft.key_points
        or not draft.difficulties
        or not draft.teaching_flow
        or not draft.assessments
        or not draft.homework
        or not draft.board_plan
        or not draft.teacher_notes
        or draft.saved
        or draft.side_effects
    ):
        violations["incomplete_lesson_delivered"] += 1
    executed.add("complete_lesson_blocks")

    question = draft.questions[0]
    if not all(
        (question.stem_plain, question.options, question.answer_value, question.solution_steps, question.final_answer)
    ):
        violations["question_completeness_lost"] += 1
    executed.add("complete_question_facts")

    if sum(phase.minutes for phase in draft.teaching_flow) != source.blueprint.duration_minutes:
        violations["alignment_broken"] += 1
    executed.add("time_total_matches")
    objective_ids = {item.objective_id for item in draft.objectives}
    activity_ids = {item for phase in draft.teaching_flow for item in phase.objective_ids}
    if not objective_ids <= activity_ids:
        violations["alignment_broken"] += 1
    executed.add("objective_activity_alignment")
    assessment_ids = {item for assessment in draft.assessments for item in assessment.objective_ids}
    if not objective_ids <= assessment_ids:
        violations["alignment_broken"] += 1
    executed.add("objective_assessment_alignment")
    if (
        not draft.integrity.source_traceability_complete
        or {item.source_kind for item in draft.source_manifest}
        != {"curriculum", "public_question", "private_resource"}
    ):
        violations["source_traceability_lost"] += 1
    executed.add("source_traceability_complete")
    if not draft.integrity.high_school_scope or "高二" not in draft.source_draft.blueprint.grade_scope:
        violations["scope_escape"] += 1
    executed.add("high_school_scope_preserved")

    _record_raise(
        violations,
        "incomplete_lesson_delivered",
        LessonDraftingError,
        lambda: LessonDrafting(source_selection=_SourceSelection(incomplete)).build(
            LessonDraftCommand(source_draft=incomplete), owner_id="teacher-a"
        ),
    )
    executed.add("incomplete_source_rejected")
    submitted = _source_draft(revision=2)
    changed = _source_draft(revision=3)
    _record_raise(
        violations,
        "source_traceability_lost",
        LessonDraftingConflict,
        lambda: LessonDrafting(source_selection=_SourceSelection(changed)).build(
            LessonDraftCommand(source_draft=submitted), owner_id="teacher-a"
        ),
    )
    executed.add("changed_revision_rejected")

    before = draft.model_dump(mode="python")
    rewritten = LessonBlockEditing(drafting=drafting).rewrite(
        LessonBlockRewriteCommand(
            draft=draft,
            target_block="homework",
            instruction="增加一道分层迁移任务",
            expected_draft_revision=1,
        ),
        owner_id="teacher-a",
    )
    if rewritten.homework == draft.homework or any(
        rewritten.model_dump(mode="python")[block] != before[block]
        for block in (
            "objectives", "key_points", "difficulties", "teaching_flow",
            "questions", "assessments", "board_plan", "teacher_notes",
        )
    ):
        violations["targeted_edit_drift"] += 1
    executed.add("targeted_rewrite_only")

    locked = draft.model_copy(deep=True)
    locked.locked_blocks = ["homework"]
    _record_raise(
        violations,
        "locked_edit_bypass",
        LessonBlockEditingConflict,
        lambda: LessonBlockEditing(drafting=drafting).rewrite(
            LessonBlockRewriteCommand(
                draft=locked,
                target_block="homework",
                instruction="调整作业",
                expected_draft_revision=1,
            ),
            owner_id="teacher-a",
        ),
    )
    executed.add("locked_block_rejected")
    tampered = draft.model_copy(deep=True)
    tampered.questions[0].final_answer = "A"
    _record_raise(
        violations,
        "question_fact_drift",
        LessonBlockEditingConflict,
        lambda: LessonBlockEditing(drafting=drafting).rewrite(
            LessonBlockRewriteCommand(
                draft=tampered,
                target_block="teacher_notes",
                instruction="补充观察点",
                expected_draft_revision=1,
            ),
            owner_id="teacher-a",
        ),
    )
    executed.add("question_facts_immutable")

    _record_raise(
        violations,
        "cross_owner_leak",
        ValidationError,
        lambda: LessonVersionSaveCommand.model_validate(
            {"draft": draft.model_dump(), "confirmed": True, "owner_id": "teacher-other"}
        ),
    )
    executed.add("browser_owner_spoof_rejected")

    versioning = LessonVersioning(database_path=tmp_path / "lesson-eval.sqlite3", drafting=drafting)
    first = versioning.save(
        LessonVersionSaveCommand(draft=draft, confirmed=True), owner_id="teacher-a"
    )
    if first.version != 1 or not first.saved or first.owner_scope != "current_owner_only":
        violations["implicit_save"] += 1
    executed.add("explicit_save_version")
    second_draft = draft.model_copy(deep=True)
    second_draft.teacher_notes = [_V2_MARKER]
    second = versioning.save(
        LessonVersionSaveCommand(
            draft=second_draft,
            lesson_plan_id=first.lesson_plan_id,
            confirmed=True,
        ),
        owner_id="teacher-a",
    )
    old = versioning.get(first.lesson_plan_id, owner_id="teacher-a", version=1)
    if second.version != 2 or _V2_MARKER in old.draft.teacher_notes:
        violations["immutable_version_drift"] += 1
    executed.add("immutable_first_version")
    if versioning.list(owner_id="teacher-a").total != 1 or versioning.list(owner_id="teacher-other").total:
        violations["cross_owner_leak"] += 1
    executed.add("owner_history_isolated")
    versioning.change_lifecycle(
        first.lesson_plan_id,
        LessonVersionLifecycleCommand(action="trash"),
        owner_id="teacher-a",
    )
    restored = versioning.change_lifecycle(
        first.lesson_plan_id,
        LessonVersionLifecycleCommand(action="restore"),
        owner_id="teacher-a",
    )
    if restored.lifecycle_state != "active":
        violations["unexpected_outcome"] += 1
    executed.add("recoverable_lifecycle")

    exporting = LessonSavedExporting(
        versioning=versioning,
        renderer=SavedLessonPlanDocumentRenderer(output_root=tmp_path / "exports"),
    )
    docx = exporting.export(
        lesson_plan_id=first.lesson_plan_id,
        version=1,
        owner_id="teacher-a",
        export_format="docx",
    )
    pdf = exporting.export(
        lesson_plan_id=first.lesson_plan_id,
        version=1,
        owner_id="teacher-a",
        export_format="pdf",
    )
    with ZipFile(docx.path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    if (
        not docx.path.read_bytes().startswith(b"PK")
        or draft.title not in xml
        or question.stem_plain not in xml
        or question.final_answer not in xml
    ):
        violations["export_snapshot_drift"] += 1
    executed.add("exact_docx_export")
    pdf_bytes = pdf.path.read_bytes()
    if not pdf_bytes.startswith(b"%PDF") or not pdf_bytes.rstrip().endswith(b"%%EOF"):
        violations["export_snapshot_drift"] += 1
    executed.add("exact_pdf_export")
    if _V2_MARKER in xml:
        violations["export_snapshot_drift"] += 1
    executed.add("later_version_not_exported")
    _record_raise(
        violations,
        "cross_owner_leak",
        LessonSavedExportingError,
        lambda: exporting.export(
            lesson_plan_id=first.lesson_plan_id,
            version=1,
            owner_id="teacher-other",
            export_format="docx",
        ),
    )
    executed.add("cross_owner_export_rejected")

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
        for token in ("lesson", "save", "export", "trash", "restore", "publish", "share")
    ):
        violations["agent_privilege_escalation"] += 1
    executed.add("agent_no_lesson_write_tool")

    if executed != case_ids:
        violations["unexpected_outcome"] += len(case_ids.symmetric_difference(executed))
    print(f"\n[m10-eval] cases={len(case_ids)} violations={violations}")
    assert violations == {key: 0 for key in violations}, violations
