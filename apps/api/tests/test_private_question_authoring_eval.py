"""Fixed M8 private question authoring evaluation; uses synthetic content only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from app.core.identity import CurrentTeacher, get_current_teacher
from app.main import app
from app.modules.curriculum import InMemoryCurriculumCatalog
from app.modules.background_jobs import BackgroundJobRegistry
from app.modules.math_verifier import MathVerifier
from app.modules.personal_question_library import (
    PersonalCategoryCreate,
    PersonalCollectionCreate,
    PersonalQuestionCopy,
    PersonalQuestionLibrary,
    PersonalQuestionLibraryConflict,
    PersonalQuestionPermanentDelete,
    PersonalQuestionSave,
    PersonalQuestionVersionCommand,
)
from app.modules.question_authoring import (
    ProviderQuestionDraft,
    ProviderQuestionSolution,
    QuestionAuthoring,
    QuestionAuthoringContext,
    QuestionAuthoringError,
    QuestionAuthoringProviderError,
    QuestionAuthoringUnavailableError,
    QuestionDesignBrief,
    QuestionDraftOption,
)
from app.modules.question_bank import QuestionBank
from app.routes.personal_question_library import get_personal_question_library


_CASES = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "test-fixtures"
    / "private-question-authoring"
    / "eval-cases.json"
)


class _SyntheticAuthoringProvider:
    name = "synthetic_m8_author"
    model = "synthetic-m8-v1"

    def __init__(
        self,
        *,
        fail: bool = False,
        unfinished: bool = False,
        university_scope: bool = False,
        embedded_options: bool = False,
        topic: str = "function",
    ) -> None:
        self.fail = fail
        self.unfinished = unfinished
        self.university_scope = university_scope
        self.embedded_options = embedded_options
        self.topic = topic

    def generate(self, context: QuestionAuthoringContext) -> ProviderQuestionDraft:
        if self.fail:
            raise QuestionAuthoringProviderError("synthetic model unavailable")
        question_type = context.question_type
        options = []
        if question_type in {"single_choice", "multiple_choice"}:
            options = [
                QuestionDraftOption(key="A", text="A. 在定义域上恒增"),
                QuestionDraftOption(key="B", text="B. 先减后增"),
                QuestionDraftOption(key="C", text="C. 在定义域上恒减"),
                QuestionDraftOption(key="D", text="D. 不是函数"),
            ]
        if question_type == "single_choice":
            answer, final = "B", "答案为 B。"
        elif question_type == "multiple_choice":
            answer, final = "A,C", "答案为 A、C。"
        elif question_type == "fill_blank":
            answer, final = "2", "最终结果为 2。"
        else:
            answer, final = "x=1", "最终解为 x=1。"
        stem = "已知函数 f(x)=x²，完成题目要求。"
        method = "定义与运算相结合"
        steps = ["根据定义整理已知条件。", "逐步运算并核对所得结论。"]
        topic_payloads = {
            "conic": (
                "已知椭圆 x²/4+y²/3=1，则该椭圆的离心率为______。",
                "1/2",
                "最终结果为 1/2。",
                "椭圆几何量计算",
                ["由标准方程得 a=2，b=√3。", "由 c²=a²-b² 得 c=1，所以 e=c/a=1/2。"],
            ),
            "probability": (
                "一枚均匀硬币连续抛掷两次，下列结论正确的是（多选）。",
                "A,C",
                "答案为 A、C。",
                "列举基本事件",
                ["列出正面与反面的四个等可能结果。", "逐项计算事件概率并选择 A、C。"],
            ),
            "sequence": (
                "等差数列 {a_n} 中，a₁=1，公差 d=2，求通项公式。",
                "a_n=2n-1",
                "最终答案为 a_n=2n-1。",
                "等差数列通项公式",
                ["使用 a_n=a₁+(n-1)d。", "代入 a₁=1、d=2，化简得 a_n=2n-1。"],
            ),
            "trigonometry": (
                "计算 sin(π/6)=______。",
                "1/2",
                "最终结果为 1/2。",
                "特殊角三角函数值",
                ["在单位圆或直角三角形中确定 π/6。", "得到 sin(π/6)=1/2。"],
            ),
            "solid_geometry": (
                "在正方体 ABCD-A₁B₁C₁D₁ 中，证明 AB∥C₁D₁。",
                "AB∥C₁D₁",
                "结论为 AB∥C₁D₁。",
                "空间平行关系证明",
                ["正方形 ABCD 中 AB∥CD。", "正方形 CDD₁C₁ 中 CD∥C₁D₁，因此 AB∥C₁D₁。"],
            ),
        }
        if self.topic in topic_payloads:
            stem, answer, final, method, steps = topic_payloads[self.topic]
        if self.topic == "probability":
            options = [
                QuestionDraftOption(key="A", text="样本空间含 4 个等可能结果"),
                QuestionDraftOption(key="B", text="恰有一次正面的概率为 1/4"),
                QuestionDraftOption(key="C", text="恰有一次正面的概率为 1/2"),
                QuestionDraftOption(key="D", text="至少一次正面的概率为 1/2"),
            ]
        if self.university_scope:
            stem = "利用马尔可夫链研究状态转移并求极限概率。"
        elif self.embedded_options and options:
            stem += "\nA. 在定义域上恒增\nB. 先减后增\nC. 在定义域上恒减\nD. 不是函数"
        return ProviderQuestionDraft(
            question_type=question_type,
            stem_plain=stem,
            stem_latex=r"已知函数 $f(x)=x^2$，完成题目要求。",
            options=options,
            answer_value=answer,
            solution_method=method,
            solution_steps=steps,
            solution_status=("needs_teacher_verification" if self.unfinished else "ready"),
            solution_issue=("synthetic unfinished solution" if self.unfinished else None),
            final_answer=final,
            authoring_intent="考查高中函数的基本性质。",
            estimated_difficulty=context.brief.target_difficulty,
            knowledge_points=["函数的基本性质"],
            assessed_methods=["定义法"],
            common_mistakes=["忽略定义域"],
        )

    def regenerate_solution(self, current: ProviderQuestionDraft) -> ProviderQuestionSolution:
        return ProviderQuestionSolution(
            solution_method="重新求解",
            solution_steps=["锁定题面。", "重新推导并核对结论。"],
            answer_value=current.answer_value,
            final_answer=current.final_answer,
        )


def _authoring(provider: _SyntheticAuthoringProvider) -> QuestionAuthoring:
    return QuestionAuthoring(
        curriculum=InMemoryCurriculumCatalog([]),
        provider=provider,
        math_verifier=MathVerifier(),
    )


def _brief(question_type: str = "single_choice") -> QuestionDesignBrief:
    return QuestionDesignBrief(
        request_text="命制一道项目自建的高中函数题。",
        grade="高二",
        question_type=question_type,
        target_difficulty=3,
    )


def _teacher(teacher_id: str):
    def dependency() -> CurrentTeacher:
        return CurrentTeacher(teacher_id=teacher_id, source="authenticated_session")

    return dependency


def test_private_question_authoring_fixed_synthetic_evaluation(tmp_path: Path) -> None:
    fixture = json.loads(_CASES.read_text(encoding="utf-8"))
    case_ids = {case["id"] for case in fixture["cases"]}
    assert fixture["evaluation_id"] == "private-question-authoring-synthetic-v1"
    assert fixture["source"] == "project-authored-synthetic"
    assert fixture["synthetic"] is True
    assert len(case_ids) == len(fixture["cases"]) == 26

    violations = {
        "unexpected_outcome": 0,
        "incomplete_draft": 0,
        "scope_escape": 0,
        "privacy_policy_leak": 0,
        "cross_owner_leak": 0,
        "public_search_leak": 0,
        "agent_privilege_escalation": 0,
        "failure_masked": 0,
        "revision_trace_missing": 0,
        "delete_guard_bypass": 0,
        "saved_question_loss": 0,
        "cancellation_masked": 0,
    }
    executed: set[str] = set()

    generated = {}
    for question_type, case_id in (
        ("single_choice", "single_choice_complete"),
        ("multiple_choice", "multiple_choice_complete"),
        ("fill_blank", "fill_blank_complete"),
        ("open_response", "open_response_complete"),
    ):
        draft = _authoring(_SyntheticAuthoringProvider()).create_draft(_brief(question_type))
        generated[question_type] = draft
        normalized_answer = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", draft.answer_value)
        normalized_final = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", draft.final_answer)
        if (
            draft.solution_status != "ready"
            or not draft.stem_plain
            or not draft.solution_steps
            or not draft.final_answer
            or normalized_answer not in normalized_final
        ):
            violations["incomplete_draft"] += 1
        if question_type in {"single_choice", "multiple_choice"} and len(draft.options) != 4:
            violations["unexpected_outcome"] += 1
        if question_type not in {"single_choice", "multiple_choice"} and draft.options:
            violations["unexpected_outcome"] += 1
        executed.add(case_id)

    for topic, question_type, case_id in (
        ("conic", "fill_blank", "conic_section_scope"),
        ("probability", "multiple_choice", "probability_scope"),
        ("sequence", "open_response", "sequence_scope"),
        ("trigonometry", "fill_blank", "trigonometry_scope"),
        ("solid_geometry", "open_response", "solid_geometry_scope"),
    ):
        draft = _authoring(_SyntheticAuthoringProvider(topic=topic)).create_draft(
            _brief(question_type)
        )
        if draft.solution_status != "ready" or not draft.solution_steps or not draft.final_answer:
            violations["incomplete_draft"] += 1
        executed.add(case_id)

    separated = _authoring(
        _SyntheticAuthoringProvider(embedded_options=True)
    ).create_draft(_brief("single_choice"))
    if "\nA." in separated.stem_plain or any(
        re.match(r"^[A-D][.、．:：)）]", option.text) for option in separated.options
    ):
        violations["unexpected_outcome"] += 1
    executed.add("choice_options_separated")

    with pytest.raises(QuestionAuthoringUnavailableError, match="不会返回半成品"):
        _authoring(_SyntheticAuthoringProvider(unfinished=True)).create_draft(
            _brief("open_response")
        )
    executed.add("unfinished_solution_rejected")

    with pytest.raises(QuestionAuthoringError, match="超出高中数学范围"):
        _authoring(_SyntheticAuthoringProvider(university_scope=True)).create_draft(
            _brief("open_response")
        )
    executed.add("university_scope_rejected")

    with pytest.raises(QuestionAuthoringUnavailableError, match="unavailable"):
        _authoring(_SyntheticAuthoringProvider(fail=True)).create_draft(_brief())
    executed.add("model_unavailable")

    registry = BackgroundJobRegistry()
    entered = Event()
    release = Event()
    checkpoint_finished = Event()

    def cancelled_runner(progress):
        entered.set()
        release.wait(timeout=2)
        try:
            progress(1, 1, "准备提交")
        finally:
            checkpoint_finished.set()
        return {"partial": True}

    cancelled_job = registry.start(
        kind="question_authoring",
        subject_id="qap_cancel_eval",
        owner_id="teacher_m8_eval",
        runner=cancelled_runner,
    )
    if not entered.wait(timeout=1):
        violations["cancellation_masked"] += 1
    cancelled = registry.cancel(
        cancelled_job.job_id, owner_id="teacher_m8_eval"
    )
    release.set()
    if not checkpoint_finished.wait(timeout=1):
        violations["cancellation_masked"] += 1
    if cancelled.status != "cancelled" or cancelled.result:
        violations["cancellation_masked"] += 1
    executed.add("background_cancelled")

    with pytest.raises(QuestionAuthoringError, match="参考母题模式尚未开放"):
        _authoring(_SyntheticAuthoringProvider()).create_draft(
            _brief().model_copy(update={"reference_question_id": "q_unverified_reference"})
        )
    executed.add("reference_rights_unverified")

    base = generated["single_choice"]
    policy = base.model_dump(mode="json")
    if (
        policy["visibility"] != "owner_only"
        or policy["public_search_allowed"]
        or policy["share_allowed"]
        or policy["commercial_use_allowed"]
        or policy["model_training_allowed"]
        or any(key in policy for key in ("owner_id", "publish", "share"))
    ):
        violations["privacy_policy_leak"] += 1
    executed.add("owner_only_policy")

    library = PersonalQuestionLibrary(tmp_path / "personal-question-library.sqlite3")
    app.dependency_overrides[get_personal_question_library] = lambda: library
    app.dependency_overrides[get_current_teacher] = _teacher("teacher_m8_eval")
    try:
        with TestClient(app) as client:
            spoof = client.post(
                "/api/v1/personal-question-library/collections",
                json={"name": "M8 评测题库", "owner_id": "teacher_other"},
            )
        if spoof.status_code != 422:
            violations["privacy_policy_leak"] += 1
    finally:
        app.dependency_overrides.clear()
    executed.add("browser_owner_spoof")

    staged = library.stage_generated_draft(base, owner_id="teacher_m8_eval")
    if library.list_questions(owner_id="teacher_m8_eval").total != 0 or staged.saved:
        violations["unexpected_outcome"] += 1
    collection = library.create_collection(
        PersonalCollectionCreate(name="M8 固定评测"), owner_id="teacher_m8_eval"
    )
    category = library.create_category(
        collection.collection_id,
        PersonalCategoryCreate(name="函数"),
        owner_id="teacher_m8_eval",
    )
    saved = library.save_authoring_draft(
        base.draft_id,
        PersonalQuestionSave(
            expected_revision=1,
            collection_id=collection.collection_id,
            category_id=category.category_id,
            name="项目自建函数题",
        ),
        owner_id="teacher_m8_eval",
    )
    if library.list_questions(owner_id="teacher_m8_eval").total != 1 or not saved.question.saved:
        violations["unexpected_outcome"] += 1
    executed.add("explicit_save_only")

    for lookup in (
        lambda: library.get_authoring_draft(base.draft_id, owner_id="teacher_other"),
        lambda: library.get_question(saved.question_id, owner_id="teacher_other"),
    ):
        with pytest.raises(KeyError):
            lookup()
    executed.add("cross_owner_isolation")

    public_bank = QuestionBank(tmp_path / "public-question-bank.sqlite3")
    if public_bank.search(query="项目自建函数题", usage_scope="teacher").total != 0:
        violations["public_search_leak"] += 1
    executed.add("public_search_isolation")

    tool_source = (
        Path(__file__).resolve().parents[3]
        / "apps"
        / "agent"
        / "src"
        / "tools"
        / "teacher-tools.ts"
    ).read_text(encoding="utf-8")
    allowlist_match = re.search(
        r"TEACHER_TOOL_ALLOWLIST[^=]*=\s*\[(.*?)\];", tool_source, re.DOTALL
    )
    tool_names = set(re.findall(r'"([a-z_]+)"', allowlist_match.group(1))) if allowlist_match else set()
    forbidden = {name for name in tool_names if any(word in name for word in ("save", "publish", "share", "delete", "admin"))}
    if "create_question_draft" not in tool_names or forbidden:
        violations["agent_privilege_escalation"] += 1
    executed.add("agent_management_forbidden")

    copied = library.copy_question(
        saved.question_id,
        PersonalQuestionCopy(
            collection_id=collection.collection_id,
            category_id=category.category_id,
            name="项目自建函数题副本",
        ),
        owner_id="teacher_m8_eval",
    )
    if copied.copied_from_question_id != saved.question_id or copied.source_draft_id == saved.source_draft_id:
        violations["revision_trace_missing"] += 1
    executed.add("copy_is_independent")

    trashed = library.trash_question(
        copied.question_id,
        PersonalQuestionVersionCommand(expected_updated_at=copied.updated_at),
        owner_id="teacher_m8_eval",
    )
    restored = library.restore_question(
        copied.question_id,
        PersonalQuestionVersionCommand(expected_updated_at=trashed.updated_at),
        owner_id="teacher_m8_eval",
    )
    if restored.lifecycle_state != "active":
        violations["unexpected_outcome"] += 1
    executed.add("trash_restore")

    with pytest.raises(PersonalQuestionLibraryConflict, match="回收站"):
        library.permanently_delete_question(
            copied.question_id,
            PersonalQuestionPermanentDelete(
                expected_updated_at=restored.updated_at,
                confirmation="永久删除我的私题",
            ),
            owner_id="teacher_m8_eval",
        )
    trashed_again = library.trash_question(
        copied.question_id,
        PersonalQuestionVersionCommand(expected_updated_at=restored.updated_at),
        owner_id="teacher_m8_eval",
    )
    library.permanently_delete_question(
        copied.question_id,
        PersonalQuestionPermanentDelete(
            expected_updated_at=trashed_again.updated_at,
            confirmation="永久删除我的私题",
        ),
        owner_id="teacher_m8_eval",
    )
    with pytest.raises(KeyError):
        library.get_question(copied.question_id, owner_id="teacher_m8_eval")
    executed.add("permanent_delete_guarded")

    deletion = library.delete_authoring_history(base.draft_id, owner_id="teacher_m8_eval")
    if not deletion.saved_question_preserved:
        violations["saved_question_loss"] += 1
    try:
        library.get_question(saved.question_id, owner_id="teacher_m8_eval")
    except KeyError:
        violations["saved_question_loss"] += 1
    executed.add("history_delete_preserves_saved")

    revision_draft = _authoring(_SyntheticAuthoringProvider()).create_draft(
        _brief("fill_blank")
    )
    library.stage_generated_draft(revision_draft, owner_id="teacher_m8_eval")
    revised = revision_draft.model_copy(
        update={"stem_plain": revision_draft.stem_plain + " 请写出计算过程。"}
    )
    library.append_teacher_revision(
        revised,
        owner_id="teacher_m8_eval",
        expected_revision=1,
        edit_summary="补充作答要求",
    )
    revisions = library.list_authoring_revisions(
        revision_draft.draft_id, owner_id="teacher_m8_eval"
    )
    if revisions.current_revision != 2 or revisions.total != 2 or {
        item.revision_source for item in revisions.items
    } != {"ai_generated", "teacher_edit"}:
        violations["revision_trace_missing"] += 1
    executed.add("revision_trace_preserved")

    if executed != case_ids:
        violations["unexpected_outcome"] += len(case_ids.symmetric_difference(executed))
    print(f"\n[m8-eval] cases={len(case_ids)} violations={violations}")
    assert violations == {key: 0 for key in violations}, violations
