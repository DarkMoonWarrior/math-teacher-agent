from __future__ import annotations

import pytest

from app.modules.curriculum import CurriculumNode, InMemoryCurriculumCatalog
from app.modules.question_authoring import (
    ProviderQuestionDraft,
    QuestionAuthoring,
    QuestionAuthoringClarificationRequired,
    QuestionAuthoringContext,
    QuestionAuthoringError,
    QuestionAuthoringProviderError,
    QuestionAuthoringUnavailableError,
    QuestionDesignBrief,
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
        fail: bool = False,
    ) -> None:
        self.question_type = question_type
        self.answer_value = answer_value
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
        return ProviderQuestionDraft(
            question_type=self.question_type,
            stem_plain="已知函数 f(x)=x²，判断其在实数范围内的单调性。",
            stem_latex=r"已知函数 $f(x)=x^2$，判断其在实数范围内的单调性。",
            options=options,
            answer_value=self.answer_value,
            solution_method="定义法",
            solution_steps=["比较自变量大小。", "判断函数值变化。"],
            final_answer="函数在负半轴递减，在正半轴递增。",
            authoring_intent="考查函数单调性的分区判断。",
            estimated_difficulty=2,
        )


def test_create_draft_resolves_curriculum_and_forces_unsaved_owner_only_state() -> None:
    provider = FakeProvider()
    authoring = QuestionAuthoring(curriculum=curriculum(), provider=provider)
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
    assert draft.verification.status == "not_run"
    assert draft.verification.math_verifier_checked is False
    assert draft.verification.teacher_review_required is True
    assert draft.difficulty_source == "model_estimated"
    assert draft.provider == "synthetic_provider"
    assert "owner_id" not in draft.model_dump(mode="json")


def test_natural_language_infers_question_type_and_reviewed_curriculum_mapping() -> None:
    provider = FakeProvider()
    authoring = QuestionAuthoring(curriculum=curriculum(), provider=provider)

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


def test_missing_knowledge_point_requires_clarification_before_model_call() -> None:
    provider = FakeProvider(question_type="open_response")
    authoring = QuestionAuthoring(curriculum=curriculum(), provider=provider)

    with pytest.raises(QuestionAuthoringClarificationRequired, match="知识点"):
        authoring.create_draft(
            QuestionDesignBrief(request_text="请给我出一道适合课堂使用的题目。")
        )

    assert provider.contexts == []


def test_reference_question_mode_fails_closed_until_rights_checks_exist() -> None:
    provider = FakeProvider()
    authoring = QuestionAuthoring(curriculum=curriculum(), provider=provider)

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
    unavailable = QuestionAuthoring(curriculum=curriculum(), provider=None)
    with pytest.raises(QuestionAuthoringUnavailableError, match="没有可用"):
        unavailable.create_draft(brief)

    failed = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(fail=True),
    )
    with pytest.raises(QuestionAuthoringUnavailableError, match="synthetic"):
        failed.create_draft(brief)

    wrong_type = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(question_type="open_response"),
    )
    with pytest.raises(QuestionAuthoringError, match="题型"):
        wrong_type.create_draft(brief)

    wrong_answer = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(answer_value="Z"),
    )
    with pytest.raises(QuestionAuthoringError, match="选项编号"):
        wrong_answer.create_draft(brief)
