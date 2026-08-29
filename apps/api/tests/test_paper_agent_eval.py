"""Fixed M9 Paper Agent evaluation; uses project-authored synthetic content only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.exam_exports import ExamPaperDocumentRenderer
from app.modules.exam_papers import (
    ExamPaperStudio,
    PaperBlueprintBrief,
    PaperBlueprintPlanning,
    PaperBlueprintPlanningError,
    PaperBlueprintSelection,
    PaperBlueprintSelectionCommand,
    PaperBlueprintSelectionError,
    PaperEditableDraftCommand,
    PaperEditableDrafting,
    PaperEditableDraftingError,
    PaperVersionSaveCommand,
)
from app.modules.exam_papers.versioning import (
    PaperSavedExporting,
    PaperSavedExportingError,
    PaperVersioning,
    PaperVersioningConflict,
)
from app.modules.question_bank.schemas import QuestionDetail, QuestionSearchPage, QuestionSummary
from app.routes.exam_papers import get_paper_blueprint_selection


_CASES = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "test-fixtures"
    / "paper-agent"
    / "eval-cases.json"
)
_SOLUTION_MARKER = "M9项目自建完整解析标记"
_ORIGINAL_STEM_MARKER = "M9项目自建原始题面标记"
_CHANGED_STEM_MARKER = "M9不应进入既有版本的新题面"


def _public_question(
    question_id: str,
    *,
    stem: str,
    question_type: str = "single_choice",
    chapter: str = "函数",
    difficulty: int = 3,
    review_status: str = "approved",
    verification_status: str = "passed",
    blockers: list[str] | None = None,
) -> QuestionSummary:
    return QuestionSummary(
        question_id=question_id,
        status="published",
        review_status=review_status,
        visibility="public",
        question_type=question_type,
        stem_plain=stem,
        answer_value="B",
        volume="必修第一册",
        chapter=chapter,
        section="项目自建评测",
        knowledge_point_ids=[chapter],
        difficulty=difficulty,
        verification_status=verification_status,
        source_document="m9-synthetic-public.json",
        source_page_start=1,
        source_page_end=1,
        license_status="public_permissive",
        publication_blockers=blockers or [],
    )


class _QuestionBank:
    def __init__(self, questions: list[QuestionSummary]) -> None:
        self.questions = questions

    def search(self, **kwargs) -> QuestionSearchPage:
        page = kwargs.get("page", 1)
        page_size = kwargs.get("page_size", 100)
        start = (page - 1) * page_size
        return QuestionSearchPage(
            items=self.questions[start : start + page_size],
            total=len(self.questions),
            page=page,
            page_size=page_size,
        )

    def get_question(self, question_id: str) -> QuestionDetail:
        summary = next(item for item in self.questions if item.question_id == question_id)
        return QuestionDetail.model_validate(
            {
                **summary.model_dump(mode="json"),
                "raw": {
                    "stem": {"plain_text": summary.stem_plain, "latex": None},
                    "options": [
                        {"key": "A", "plain_text": "项目自建干扰项", "latex": None},
                        {"key": "B", "plain_text": "项目自建正确项", "latex": None},
                    ] if summary.question_type in {"single_choice", "multiple_choice"} else [],
                    "solutions": [
                        {
                            "method": "项目自建确定性方法",
                            "steps_latex": [_SOLUTION_MARKER, "逐步核对最终答案。"],
                            "final_answer": summary.answer_value,
                        }
                    ],
                },
                "reviews": [],
                "images": [],
                "revision_count": 0,
            }
        )

    def image_path(self, question_id: str, image_id: str):
        raise KeyError((question_id, image_id))


class _PersonalLibrary:
    def __init__(self, questions: dict[str, object] | None = None) -> None:
        self.questions = questions or {}

    def get_question(self, question_id: str, *, owner_id: str):
        value = self.questions.get(f"{owner_id}:{question_id}")
        if value is None:
            raise KeyError(question_id)
        return value


def _private_question(
    question_id: str,
    *,
    question_type: str,
    knowledge_point: str,
) -> object:
    draft = SimpleNamespace(
        solution_status="ready",
        verification=SimpleNamespace(
            status="teacher_review_required",
            math_verifier_status="unsupported",
            checks=[SimpleNamespace(status="passed")],
        ),
        stem_plain=f"项目自建 {knowledge_point} {question_id} 完整题面。",
        stem_latex=None,
        question_type=question_type,
        answer_value="B" if question_type in {"single_choice", "multiple_choice"} else "2",
        curriculum=SimpleNamespace(
            volume="必修第一册",
            chapter=knowledge_point,
            section="项目自建评测",
        ),
        knowledge_points=[knowledge_point],
        estimated_difficulty=3,
        options=[
            SimpleNamespace(key="A", text="项目自建干扰项"),
            SimpleNamespace(key="B", text="项目自建正确项"),
        ] if question_type in {"single_choice", "multiple_choice"} else [],
        solution_method="项目自建确定性方法",
        solution_steps=[_SOLUTION_MARKER, "逐步核对最终答案。"],
        final_answer="B" if question_type in {"single_choice", "multiple_choice"} else "2",
        source_document="教师私有题库",
    )
    return SimpleNamespace(
        question_id=question_id,
        lifecycle_state="active",
        question=draft,
        name=f"项目自建 {knowledge_point} 私题",
        selected_revision=1,
    )


def _command(
    *,
    count: int = 2,
    score: float = 10,
    public_ids: list[str] | None = None,
    private_ids: list[str] | None = None,
    knowledge_points: list[str] | None = None,
) -> PaperBlueprintSelectionCommand:
    return PaperBlueprintSelectionCommand.model_validate(
        {
            "blueprint": {
                "title": "M9 项目自建函数测验",
                "grade_scope": "高二",
                "teaching_usage": "专题测验",
                "duration_minutes": 30,
                "target_score": score,
                "difficulty_profile": "balanced",
                "knowledge_points": knowledge_points or ["函数"],
                "sections": [
                    {
                        "section_id": "single",
                        "title": "单项选择题",
                        "question_type": "single_choice",
                        "question_count": count,
                        "target_score": score,
                    }
                ],
            },
            "selected_public_question_ids": public_ids or [],
            "selected_private_question_ids": private_ids or [],
        }
    )


def _four_question_command(question_ids: list[str]) -> PaperBlueprintSelectionCommand:
    return PaperBlueprintSelectionCommand.model_validate(
        {
            "blueprint": {
                "title": "M9 项目自建显式选题测验",
                "grade_scope": "高二",
                "teaching_usage": "专题测验",
                "duration_minutes": 60,
                "target_score": 40,
                "difficulty_profile": "balanced",
                "knowledge_points": ["函数"],
                "sections": [
                    {"section_id": "choice", "title": "单项选择题", "question_type": "single_choice", "question_count": 1, "target_score": 5},
                    {"section_id": "fill", "title": "填空题", "question_type": "fill_blank", "question_count": 2, "target_score": 10},
                    {"section_id": "open", "title": "解答题", "question_type": "open_response", "question_count": 1, "target_score": 25},
                ],
            },
            "selected_private_question_ids": question_ids,
        }
    )


def _docx_text(path: Path) -> str:
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    return "".join(root.itertext())


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


def test_paper_agent_fixed_synthetic_evaluation(tmp_path: Path) -> None:
    fixture = json.loads(_CASES.read_text(encoding="utf-8"))
    case_ids = {case["id"] for case in fixture["cases"]}
    assert fixture["evaluation_id"] == "paper-agent-synthetic-v1"
    assert fixture["source"] == "project-authored-synthetic"
    assert fixture["synthetic"] is True
    assert len(case_ids) == len(fixture["cases"]) == 28

    violations = {
        "unexpected_outcome": 0,
        "scope_escape": 0,
        "trust_gate_bypass": 0,
        "rights_gate_bypass": 0,
        "cross_owner_leak": 0,
        "explicit_selection_lost": 0,
        "duplicate_inclusion": 0,
        "supply_gap_masked": 0,
        "coverage_overstated": 0,
        "draft_state_escalation": 0,
        "forged_layout_accepted": 0,
        "stale_draft_accepted": 0,
        "immutable_version_drift": 0,
        "export_answer_leak": 0,
        "agent_privilege_escalation": 0,
    }
    executed: set[str] = set()

    planning = PaperBlueprintPlanning()
    explicit_blueprint = planning.plan(
        PaperBlueprintBrief(
            brief="组一份高二期中卷，120 分钟，总分 150 分，覆盖函数、导数与圆锥曲线，中等偏难"
        )
    )
    if (
        explicit_blueprint.status != "draft"
        or explicit_blueprint.confirmed
        or explicit_blueprint.saved
        or sum(section.target_score for section in explicit_blueprint.sections) != 150
        or explicit_blueprint.side_effects
    ):
        violations["unexpected_outcome"] += 1
    executed.add("explicit_midterm_blueprint")

    defaults = planning.plan(PaperBlueprintBrief(brief="组一份导数专题测验，含 3 道解答题"))
    if not defaults.assumptions or not all(
        any(label in item for item in defaults.assumptions)
        for label in ("年级", "考试时间", "总分")
    ):
        violations["unexpected_outcome"] += 1
    executed.add("visible_defaults_blueprint")

    _record_raise(
        violations,
        "scope_escape",
        PaperBlueprintPlanningError,
        lambda: planning.plan(PaperBlueprintBrief(brief="组一份大学数学分析与傅里叶分析试卷")),
    )
    executed.add("university_scope_rejected")

    good = _public_question("public-good", stem=_ORIGINAL_STEM_MARKER + "，函数零点为（ ）。")
    review_blocked = _public_question(
        "public-review-blocked",
        stem="项目自建待审核公共题。",
        review_status="pending",
    )
    rights_blocked = _public_question(
        "public-rights-blocked",
        stem="项目自建权利阻断公共题。",
        blockers=["commercial_rights_required"],
    )
    verification_blocked = _public_question(
        "public-verification-blocked",
        stem="项目自建验证失败公共题。",
        verification_status="failed",
    )
    second = _public_question("public-second", stem="项目自建函数最值题。", difficulty=4)
    bank = _QuestionBank([good, review_blocked, rights_blocked, verification_blocked, second])
    selection = PaperBlueprintSelection(
        question_bank=bank,
        personal_question_library=_PersonalLibrary(),
    )
    catalog_ids = {item.question_id for item in selection.list_public_candidates(owner_id="teacher-m9").items}
    if "public-good" not in catalog_ids:
        violations["trust_gate_bypass"] += 1
    executed.add("public_candidate_passed")
    if "public-review-blocked" in catalog_ids:
        violations["trust_gate_bypass"] += 1
    executed.add("public_review_blocked")
    if "public-rights-blocked" in catalog_ids:
        violations["rights_gate_bypass"] += 1
    executed.add("public_rights_blocked")
    if "public-verification-blocked" in catalog_ids:
        violations["trust_gate_bypass"] += 1
    executed.add("public_verification_blocked")

    explicit_public = selection.select(
        _command(count=1, score=5, public_ids=["public-good"], knowledge_points=["集合"]),
        owner_id="teacher-m9",
    )
    if explicit_public.actual_question_count != 1 or explicit_public.items[0].question_id != "public-good":
        violations["explicit_selection_lost"] += 1
    executed.add("explicit_public_selected")

    private_items = [
        _private_question("private-choice", question_type="single_choice", knowledge_point="集合"),
        _private_question("private-fill-a", question_type="fill_blank", knowledge_point="数列"),
        _private_question("private-fill-b", question_type="fill_blank", knowledge_point="圆锥曲线"),
        _private_question("private-open", question_type="open_response", knowledge_point="导数"),
    ]
    personal = _PersonalLibrary(
        {f"teacher-m9:{item.question_id}": item for item in private_items}
        | {"teacher-other:private-other": _private_question("private-other", question_type="single_choice", knowledge_point="函数")}
    )
    private_selection = PaperBlueprintSelection(
        question_bank=_QuestionBank([]),
        personal_question_library=personal,
    )
    one_private = private_selection.select(
        _command(count=1, score=5, private_ids=["private-choice"]),
        owner_id="teacher-m9",
    )
    if (
        one_private.actual_question_count != 1
        or one_private.items[0].owner_scope != "current_owner_only"
        or one_private.items[0].copied
    ):
        violations["cross_owner_leak"] += 1
    executed.add("explicit_private_selected")

    all_private = private_selection.select(
        _four_question_command([item.question_id for item in private_items]),
        owner_id="teacher-m9",
    )
    if all_private.actual_question_count != 4 or all_private.unselected_private_question_ids:
        violations["explicit_selection_lost"] += 1
    executed.add("explicit_private_soft_scope_retained")

    _record_raise(
        violations,
        "cross_owner_leak",
        PaperBlueprintSelectionError,
        lambda: private_selection.select(
            _command(count=1, score=5, private_ids=["private-other"]),
            owner_id="teacher-m9",
        ),
    )
    executed.add("cross_owner_private_rejected")

    duplicate_selection = PaperBlueprintSelection(
        question_bank=_QuestionBank(
            [
                _public_question("duplicate-a", stem="1. 项目自建函数 f(x)=x+1 的零点是（ ）。"),
                _public_question("duplicate-b", stem="项目自建函数 f(x)=x+1 的零点是（ ）。"),
            ]
        ),
        personal_question_library=_PersonalLibrary(),
    ).select(_command(), owner_id="teacher-m9")
    if duplicate_selection.actual_question_count != 1 or not duplicate_selection.similarity_exclusions:
        violations["duplicate_inclusion"] += 1
    executed.add("duplicate_excluded")

    gap = PaperBlueprintSelection(
        question_bank=_QuestionBank([good]),
        personal_question_library=_PersonalLibrary(),
    ).select(_command(count=3, score=15), owner_id="teacher-m9")
    if (
        gap.selection_complete
        or not gap.gaps
        or gap.gaps[0].missing_count != 2
        or gap.auto_authoring_used
        or gap.side_effects
    ):
        violations["supply_gap_masked"] += 1
    executed.add("truthful_supply_gap")

    hard_questions = [
        _public_question("hard-a", stem="已知二次函数顶点与对称轴，求参数的取值范围。", difficulty=5),
        _public_question("hard-b", stem="讨论指数函数与直线交点个数随参数的变化。", difficulty=5),
    ]
    coverage = PaperBlueprintSelection(
        question_bank=_QuestionBank(hard_questions),
        personal_question_library=_PersonalLibrary(),
    ).select(_command(knowledge_points=["函数", "导数"]), owner_id="teacher-m9")
    status_by_point = {item.knowledge_point: item.status for item in coverage.coverage_audit.knowledge_points}
    if status_by_point.get("导数") != "missing" or coverage.coverage_audit.coverage_complete:
        violations["coverage_overstated"] += 1
    executed.add("knowledge_gap_visible")
    if coverage.coverage_audit.difficulty_status != "deviated":
        violations["coverage_overstated"] += 1
    executed.add("difficulty_deviation_visible")

    complete_bank = _QuestionBank([good, second])
    complete_selection = PaperBlueprintSelection(
        question_bank=complete_bank,
        personal_question_library=_PersonalLibrary(),
    )
    drafting = PaperEditableDrafting(selection=complete_selection)
    draft_command = PaperEditableDraftCommand(selection_request=_command(), edits=[])
    draft = drafting.build(draft_command, owner_id="teacher-m9")
    if draft.saved or draft.version_created or draft.export_ready or draft.side_effects:
        violations["draft_state_escalation"] += 1
    executed.add("draft_unsaved")

    forged_command = PaperEditableDraftCommand.model_validate(
        {
            "selection_request": _command().model_dump(mode="json"),
            "edits": [
                {"question_id": "forged-question", "position": 1, "section_id": "single", "score": 10}
            ],
        }
    )
    _record_raise(
        violations,
        "forged_layout_accepted",
        PaperEditableDraftingError,
        lambda: drafting.build(forged_command, owner_id="teacher-m9"),
    )
    executed.add("forged_layout_rejected")
    if (
        len(draft.specification.question_to_dimensions) != 2
        or not any(row.dimension == "knowledge_point" for row in draft.specification.dimension_to_questions)
    ):
        violations["unexpected_outcome"] += 1
    executed.add("bidirectional_specification")

    app.dependency_overrides[get_paper_blueprint_selection] = lambda: complete_selection
    app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-m9",
        source="authenticated_session",
    )
    try:
        response = TestClient(app).post(
            "/api/v1/exam-papers/blueprints/select",
            json={
                **_command().model_dump(mode="json"),
                "owner_id": "teacher-other",
                "verification_policy": "bypass",
            },
        )
    finally:
        app.dependency_overrides.clear()
    if response.status_code != 422:
        violations["cross_owner_leak"] += 1
    executed.add("browser_owner_trust_spoof")

    studio = ExamPaperStudio(
        database_path=tmp_path / "paper-versions.sqlite3",
        asset_root=tmp_path / "paper-assets",
        question_bank=complete_bank,
    )
    versioning = PaperVersioning(drafting=drafting, studio=studio)
    exporting = PaperSavedExporting(
        studio=studio,
        renderer=ExamPaperDocumentRenderer(
            output_root=tmp_path / "exports",
            asset_root=tmp_path / "paper-assets",
        ),
    )
    saved = versioning.save(
        PaperVersionSaveCommand(
            draft_command=draft_command,
            expected_draft_fingerprint=draft.draft_fingerprint,
        ),
        owner_id="teacher-m9",
    )
    if not saved.saved or not saved.version_created or saved.version != 1:
        violations["draft_state_escalation"] += 1
    executed.add("explicit_save_version")

    _record_raise(
        violations,
        "stale_draft_accepted",
        PaperVersioningConflict,
        lambda: versioning.save(
            PaperVersionSaveCommand(
                draft_command=draft_command,
                expected_draft_fingerprint="0" * 64,
            ),
            owner_id="teacher-m9",
        ),
    )
    executed.add("stale_fingerprint_rejected")

    _record_raise(
        violations,
        "cross_owner_leak",
        PaperSavedExportingError,
        lambda: exporting.export(
            paper_id=saved.exam_paper_id,
            version=1,
            owner_id="teacher-other",
            export_format="docx",
            edition="student",
        ),
    )
    executed.add("cross_owner_saved_export_rejected")

    complete_bank.questions[0] = _public_question(
        "public-good",
        stem=_CHANGED_STEM_MARKER,
    )
    student = exporting.export(
        paper_id=saved.exam_paper_id,
        version=1,
        owner_id="teacher-m9",
        export_format="docx",
        edition="student",
    )
    answer = exporting.export(
        paper_id=saved.exam_paper_id,
        version=1,
        owner_id="teacher-m9",
        export_format="docx",
        edition="answer",
    )
    blueprint = exporting.export(
        paper_id=saved.exam_paper_id,
        version=1,
        owner_id="teacher-m9",
        export_format="docx",
        edition="blueprint",
    )
    student_text = _docx_text(student.path)
    answer_text = _docx_text(answer.path)
    blueprint_text = _docx_text(blueprint.path)
    if _ORIGINAL_STEM_MARKER not in student_text or _CHANGED_STEM_MARKER in student_text:
        violations["immutable_version_drift"] += 1
    executed.add("immutable_snapshot")
    if _SOLUTION_MARKER in student_text:
        violations["export_answer_leak"] += 1
    executed.add("student_export_no_solution")
    if _SOLUTION_MARKER not in answer_text:
        violations["unexpected_outcome"] += 1
    executed.add("answer_export_with_solution")
    if "双向细目表" not in blueprint_text or "教学维度到题目" not in blueprint_text:
        violations["unexpected_outcome"] += 1
    executed.add("blueprint_export_bidirectional")
    if len(saved.available_exports) != 6:
        violations["unexpected_outcome"] += 1
    executed.add("six_export_contract")

    tool_source = (
        Path(__file__).resolve().parents[3]
        / "apps"
        / "agent"
        / "src"
        / "tools"
        / "teacher-tools.ts"
    ).read_text(encoding="utf-8")
    allowlist_match = re.search(
        r"TEACHER_TOOL_ALLOWLIST[^=]*=\s*\[(.*?)\];",
        tool_source,
        re.DOTALL,
    )
    tool_names = set(re.findall(r'"([a-z_]+)"', allowlist_match.group(1))) if allowlist_match else set()
    forbidden = {
        name
        for name in tool_names
        if any(token in name for token in ("paper", "exam", "save", "export", "publish", "delete"))
    }
    if forbidden:
        violations["agent_privilege_escalation"] += 1
    executed.add("agent_no_paper_write_tool")

    if executed != case_ids:
        violations["unexpected_outcome"] += len(case_ids.symmetric_difference(executed))
    print(f"\n[m9-eval] cases={len(case_ids)} violations={violations}")
    assert violations == {key: 0 for key in violations}, violations
