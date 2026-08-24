from __future__ import annotations

import pytest

from app.modules.curriculum import CurriculumNode, InMemoryCurriculumCatalog
from app.modules.math_verifier import MathVerifier, VerificationReport
from app.modules.question_authoring import (
    ProviderQuestionDraft,
    QuestionAuthoring,
    QuestionAuthoringClarificationRequired,
    QuestionAuthoringContext,
    QuestionAuthoringError,
    QuestionAuthoringProviderError,
    QuestionAuthoringUnavailableError,
    QuestionDesignBrief,
    QuestionDraftEditableContent,
    QuestionDraftOption,
)


def curriculum() -> InMemoryCurriculumCatalog:
    common = {
        "description": "",
        "prerequisite_node_ids": [],
        "primary_competencies": [],
        "typical_question_types": [],
        "common_errors": [],
        "gaokao_priority": "medium",
        "status": "reviewed",
        "reviewed_by": "synthetic_teacher",
    }
    return InMemoryCurriculumCatalog(
        [
            CurriculumNode(
                node_id="root",
                parent_id=None,
                volume="高中数学",
                node_type="root",
                code="0",
                name="高中数学",
                **common,
            ),
            CurriculumNode(
                node_id="vol_1",
                parent_id="root",
                volume="必修第一册",
                node_type="volume",
                code="1",
                name="必修第一册",
                **common,
            ),
            CurriculumNode(
                node_id="ch_1",
                parent_id="vol_1",
                volume="必修第一册",
                node_type="chapter",
                code="1.1",
                name="函数的概念与性质",
                **common,
            ),
            CurriculumNode(
                node_id="sec_1",
                parent_id="ch_1",
                volume="必修第一册",
                node_type="section",
                code="1.1.1",
                name="函数单调性",
                **common,
            ),
            CurriculumNode(
                node_id="kp_monotonicity",
                parent_id="sec_1",
                volume="必修第一册",
                node_type="knowledge_point",
                code="1.1.1.1",
                name="函数单调性的判断",
                **common,
            ),
            CurriculumNode(
                node_id="ch_ellipse",
                parent_id="vol_1",
                volume="选择性必修第一册",
                node_type="chapter",
                code="3.1",
                name="圆锥曲线的方程",
                **common,
            ),
            CurriculumNode(
                node_id="sec_ellipse",
                parent_id="ch_ellipse",
                volume="选择性必修第一册",
                node_type="section",
                code="3.1.1",
                name="椭圆",
                **common,
            ),
            CurriculumNode(
                node_id="kp_ellipse_geometry",
                parent_id="sec_ellipse",
                volume="选择性必修第一册",
                node_type="knowledge_point",
                code="3.1.1.3",
                name="椭圆的几何性质",
                **common,
            ),
        ]
    )


class FakeProvider:
    name = "synthetic_provider"
    model = "synthetic-author-v1"

    def __init__(
        self,
        *,
        question_type: str = "single_choice",
        answer_value: str = "B",
        final_answer: str = "函数在负半轴递减，在正半轴递增。",
        duplicate_option_text: bool = False,
        estimated_difficulty: int = 2,
        curriculum_node_id: str | None = None,
        knowledge_points: list[str] | None = None,
        assessed_methods: list[str] | None = None,
        common_mistakes: list[str] | None = None,
        fail: bool = False,
    ) -> None:
        self.question_type = question_type
        self.answer_value = answer_value
        self.final_answer = final_answer
        self.duplicate_option_text = duplicate_option_text
        self.estimated_difficulty = estimated_difficulty
        self.curriculum_node_id = curriculum_node_id
        self.knowledge_points = knowledge_points or []
        self.assessed_methods = assessed_methods or []
        self.common_mistakes = common_mistakes or []
        self.fail = fail
        self.contexts: list[QuestionAuthoringContext] = []

    def generate(self, context: QuestionAuthoringContext) -> ProviderQuestionDraft:
        self.contexts.append(context)
        if self.fail:
            raise QuestionAuthoringProviderError("synthetic model unavailable")
        options = (
            [
                QuestionDraftOption(key="A", text="在定义域上恒增"),
                QuestionDraftOption(key="B", text="先减后增"),
                QuestionDraftOption(key="C", text="在定义域上恒减"),
                QuestionDraftOption(key="D", text="不是函数"),
            ]
            if self.question_type in {"single_choice", "multiple_choice"}
            else []
        )
        if self.duplicate_option_text and options:
            options[-1] = QuestionDraftOption(key="D", text=options[-2].text)
        payload = dict(
            question_type=self.question_type,
            stem_plain="已知函数 f(x)=x²，判断其在实数范围内的单调性。",
            stem_latex=r"已知函数 $f(x)=x^2$，判断其在实数范围内的单调性。",
            options=options,
            answer_value=self.answer_value,
            solution_method="定义法",
            solution_steps=["比较自变量大小。", "判断函数值变化。"],
            final_answer=self.final_answer,
            authoring_intent="考查函数单调性的分区判断。",
            estimated_difficulty=self.estimated_difficulty,
        )
        if self.curriculum_node_id is not None:
            payload.update(
                curriculum_node_id=self.curriculum_node_id,
                knowledge_points=self.knowledge_points,
                assessed_methods=self.assessed_methods,
                common_mistakes=self.common_mistakes,
            )
        return ProviderQuestionDraft(**payload)


def test_create_draft_resolves_curriculum_and_forces_unsaved_owner_only_state() -> None:
    provider = FakeProvider()
    authoring = QuestionAuthoring(
        curriculum=curriculum(), provider=provider, math_verifier=MathVerifier()
    )
    brief = QuestionDesignBrief(
        request_text="命制一道函数单调性的单选题，用于课堂诊断。",
        curriculum_node_id="kp_monotonicity",
        question_type="single_choice",
        target_difficulty=2,
    )

    draft = authoring.create_draft(brief)

    assert draft.question_type == "single_choice"
    assert draft.curriculum.node_id == "kp_monotonicity"
    assert draft.curriculum.mapping_source == "teacher_selected"
    assert draft.curriculum.match_confidence == 1
    assert draft.source_type == "ai_generated"
    assert draft.visibility == "owner_only"
    assert draft.saved is False
    assert draft.public_search_allowed is False
    assert draft.share_allowed is False
    assert draft.commercial_use_allowed is False
    assert draft.model_training_allowed is False
    assert draft.verification.status == "teacher_review_required"
    assert draft.verification.math_verifier_status == "unsupported"
    assert draft.verification.math_verifier_checked is False
    assert draft.verification.teacher_review_required is True
    assert draft.verification.verifier_version == MathVerifier.VERSION
    checks = {check.code: check for check in draft.verification.checks}
    assert set(checks) == {
        "solvability",
        "answer_solution_consistency",
        "choice_answer_cardinality",
        "distractor_quality",
        "math_verifier",
        "difficulty_disclosure",
    }
    assert checks["choice_answer_cardinality"].status == "passed"
    assert checks["math_verifier"].status == "inconclusive"
    assert checks["math_verifier"].capability == "unsupported"
    assert draft.difficulty_source == "model_estimated"
    assert draft.provider == "synthetic_provider"
    assert "owner_id" not in draft.model_dump(mode="json")


def test_teacher_revision_rechecks_structure_and_cannot_supply_trust_evidence() -> None:
    authoring = QuestionAuthoring(
        curriculum=curriculum(), provider=FakeProvider(), math_verifier=MathVerifier()
    )
    draft = authoring.create_draft(
        QuestionDesignBrief(
            request_text="命制一道函数单调性的单选题，用于课堂诊断。",
            curriculum_node_id="kp_monotonicity",
            question_type="single_choice",
            target_difficulty=2,
        )
    )

    revised = authoring.revise_draft(
        draft,
        QuestionDraftEditableContent(
            question_type=draft.question_type,
            stem_plain="教师修改后的题干：判断函数 f(x)=x² 的单调性。",
            stem_latex=draft.stem_latex,
            options=draft.options,
            answer_value="B",
            solution_method=draft.solution_method,
            solution_steps=draft.solution_steps,
            final_answer="答案为 A。",
            authoring_intent=draft.authoring_intent,
        ),
    )

    assert revised.draft_id == draft.draft_id
    assert revised.saved is False
    assert revised.visibility == "owner_only"
    assert revised.verification.status == "checks_failed"
    checks = {item.code: item for item in revised.verification.checks}
    assert checks["answer_solution_consistency"].status == "failed"
    assert revised.verification.math_verifier_status == "unsupported"
    assert any("教师编辑" in warning for warning in revised.warnings)


def test_natural_language_infers_question_type_and_reviewed_curriculum_mapping() -> None:
    provider = FakeProvider()
    authoring = QuestionAuthoring(
        curriculum=curriculum(), provider=provider, math_verifier=MathVerifier()
    )

    draft = authoring.create_draft(
        QuestionDesignBrief(
            request_text="围绕函数单调性的判断出一道单选题，难度偏基础。"
        )
    )

    assert draft.question_type == "single_choice"
    assert draft.curriculum.node_id == "kp_monotonicity"
    assert draft.curriculum.mapping_source == "brief_match"
    assert draft.curriculum.curriculum_status == "reviewed"
    assert provider.contexts[0].question_type == "single_choice"
    assert any("推断" in warning for warning in draft.warnings)


def test_model_can_infer_curriculum_and_pedagogy_after_generation() -> None:
    provider = FakeProvider(
        question_type="fill_blank",
        curriculum_node_id="kp_ellipse_geometry",
        knowledge_points=["椭圆离心率", "参数范围"],
        assessed_methods=["利用离心率定义建立参数关系"],
        common_mistakes=["混淆半焦距 c 与焦距 2c"],
    )
    authoring = QuestionAuthoring(
        curriculum=curriculum(), provider=provider, math_verifier=MathVerifier()
    )

    draft = authoring.create_draft(
        QuestionDesignBrief(
            request_text="命制一道考试用的椭圆离心率填空题。",
            question_type="fill_blank",
            target_difficulty=5,
        )
    )

    assert provider.contexts[0].curriculum is None
    assert any(
        item.node_id == "kp_ellipse_geometry"
        for item in provider.contexts[0].curriculum_options
    )
    assert draft.curriculum is not None
    assert draft.curriculum.node_id == "kp_ellipse_geometry"
    assert draft.curriculum.mapping_source == "agent_inferred"
    assert draft.curriculum.mapping_status == "pending_teacher_confirmation"
    assert draft.knowledge_points == ["椭圆离心率", "参数范围"]
    assert draft.assessed_methods == ["利用离心率定义建立参数关系"]
    assert draft.common_mistakes == ["混淆半焦距 c 与焦距 2c"]
    assert draft.pedagogy_source == "model_generated"
    assert draft.saved is False
    assert draft.visibility == "owner_only"


def test_teacher_can_confirm_inferred_curriculum_and_edit_derived_metadata() -> None:
    authoring = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(
            question_type="fill_blank",
            curriculum_node_id="kp_ellipse_geometry",
            knowledge_points=["椭圆离心率"],
            assessed_methods=["定义法"],
            common_mistakes=["混淆焦距与半焦距"],
        ),
        math_verifier=MathVerifier(),
    )
    draft = authoring.create_draft(
        QuestionDesignBrief(
            request_text="命制一道椭圆离心率填空题。",
            question_type="fill_blank",
        )
    )

    revised = authoring.revise_draft(
        draft,
        QuestionDraftEditableContent(
            question_type=draft.question_type,
            stem_plain=draft.stem_plain,
            stem_latex=draft.stem_latex,
            options=draft.options,
            answer_value=draft.answer_value,
            solution_method=draft.solution_method,
            solution_steps=draft.solution_steps,
            final_answer=draft.final_answer,
            authoring_intent=draft.authoring_intent,
            knowledge_points=["离心率定义", "参数范围"],
            assessed_methods=["由 e=c/a 建立关系"],
            common_mistakes=["误把 2c 当作 c"],
            curriculum_confirmation_node_id="kp_ellipse_geometry",
        ),
    )

    assert revised.curriculum is not None
    assert revised.curriculum.mapping_source == "teacher_selected"
    assert revised.curriculum.mapping_status == "teacher_confirmed"
    assert revised.knowledge_points == ["离心率定义", "参数范围"]
    assert revised.pedagogy_source == "teacher_edited"


def test_unknown_model_curriculum_is_discarded_without_blocking_private_draft() -> None:
    draft = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(
            question_type="fill_blank",
            curriculum_node_id="model_invented_node",
        ),
        math_verifier=MathVerifier(),
    ).create_draft(
        QuestionDesignBrief(
            request_text="命制一道考试用填空题。",
            question_type="fill_blank",
        )
    )

    assert draft.curriculum is None
    assert draft.saved is False
    assert any("不在受控目录" in warning for warning in draft.warnings)


def test_reference_question_mode_fails_closed_until_rights_checks_exist() -> None:
    provider = FakeProvider()
    authoring = QuestionAuthoring(
        curriculum=curriculum(), provider=provider, math_verifier=MathVerifier()
    )

    with pytest.raises(QuestionAuthoringError, match="改编权利"):
        authoring.create_draft(
            QuestionDesignBrief(
                request_text="参考这道题命制一道函数单调性变式。",
                curriculum_node_id="kp_monotonicity",
                question_type="single_choice",
                reference_question_id="q_public_1",
            )
        )

    assert provider.contexts == []


def test_model_unavailable_and_malformed_structure_remain_honest_failures() -> None:
    brief = QuestionDesignBrief(
        request_text="命制一道函数单调性的单选题。",
        curriculum_node_id="kp_monotonicity",
        question_type="single_choice",
    )
    unavailable = QuestionAuthoring(
        curriculum=curriculum(), provider=None, math_verifier=MathVerifier()
    )
    with pytest.raises(QuestionAuthoringUnavailableError, match="没有可用"):
        unavailable.create_draft(brief)

    failed = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(fail=True),
        math_verifier=MathVerifier(),
    )
    with pytest.raises(QuestionAuthoringUnavailableError, match="synthetic"):
        failed.create_draft(brief)

    wrong_type = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(question_type="open_response"),
        math_verifier=MathVerifier(),
    )
    with pytest.raises(QuestionAuthoringError, match="题型"):
        wrong_type.create_draft(brief)

    wrong_answer = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(answer_value="Z"),
        math_verifier=MathVerifier(),
    )
    with pytest.raises(QuestionAuthoringError, match="选项编号"):
        wrong_answer.create_draft(brief)


def test_trust_checks_block_clear_choice_contract_failures() -> None:
    brief = QuestionDesignBrief(
        request_text="命制一道函数单调性的单选题。",
        curriculum_node_id="kp_monotonicity",
        question_type="single_choice",
    )
    cases = [
        (FakeProvider(answer_value="A,B"), "choice_answer_cardinality"),
        (FakeProvider(final_answer="答案为 C"), "answer_solution_consistency"),
        (FakeProvider(duplicate_option_text=True), "distractor_quality"),
    ]
    for provider, failed_code in cases:
        draft = QuestionAuthoring(
            curriculum=curriculum(),
            provider=provider,
            math_verifier=MathVerifier(),
        ).create_draft(brief)
        assert draft.verification.status == "checks_failed"
        failed = {
            check.code for check in draft.verification.checks if check.status == "failed"
        }
        assert failed_code in failed
        assert draft.saved is False
        assert draft.visibility == "owner_only"


def test_difficulty_gap_is_disclosed_without_becoming_math_evidence() -> None:
    draft = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(estimated_difficulty=5),
        math_verifier=MathVerifier(),
    ).create_draft(
        QuestionDesignBrief(
            request_text="命制一道函数单调性的单选题。",
            curriculum_node_id="kp_monotonicity",
            question_type="single_choice",
            target_difficulty=1,
        )
    )

    check = next(
        item for item in draft.verification.checks if item.code == "difficulty_disclosure"
    )
    assert check.status == "inconclusive"
    assert check.evidence_source == "model_estimate"
    assert draft.verification.math_verifier_status == "unsupported"
    assert draft.verification.status == "teacher_review_required"


def test_math_verifier_does_not_accept_uncontrolled_generated_prose() -> None:
    verifier = MathVerifier()
    assert verifier.supports(
        {
            "question_id": "qad_synthetic",
            "stem_plain": "一道模型生成题",
            "source_answer": "B",
        }
    ) is False
    assert verifier.supports(
        {"verification_spec": {"rule": "line_cubic_intersection_count"}}
    ) is True
    assert verifier.supports(
        {"verification_spec": {"rule": "model_invented_rule"}}
    ) is False


def test_supported_math_verifier_evidence_is_preserved_without_skipping_teacher_review() -> None:
    class SyntheticSupportedVerifier(MathVerifier):
        VERSION = "synthetic-math-v1"

        def supports(self, candidate: dict) -> bool:
            assert "verification_spec" not in candidate
            return True

        def verify(self, candidate: dict) -> VerificationReport:
            return VerificationReport(
                question_id=candidate["question_id"],
                status="passed",
                computed_answer="B",
                computed_canonical_value="option:B",
                source_answer="B",
                matched_option="B",
                method="synthetic_independent_rule",
                details=["synthetic 独立规则得到 B。"],
                evidence={"result": "B"},
                verifier_version=self.VERSION,
            )

    draft = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(),
        math_verifier=SyntheticSupportedVerifier(),
    ).create_draft(
        QuestionDesignBrief(
            request_text="命制一道函数单调性的单选题。",
            curriculum_node_id="kp_monotonicity",
            question_type="single_choice",
        )
    )

    math_check = next(
        item for item in draft.verification.checks if item.code == "math_verifier"
    )
    assert math_check.status == "passed"
    assert math_check.evidence_source == "math_verifier"
    assert draft.verification.math_verifier_checked is True
    assert draft.verification.math_verifier_status == "passed"
    assert draft.verification.verifier_version == "synthetic-math-v1"
    assert draft.verification.status == "teacher_review_required"
