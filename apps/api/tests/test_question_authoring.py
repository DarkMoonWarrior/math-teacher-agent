from __future__ import annotations

import json
from collections import Counter
from threading import Lock

import pytest

from app.modules.curriculum import CurriculumNode, InMemoryCurriculumCatalog
from app.modules.math_verifier import MathVerifier, VerificationReport
from app.modules.question_authoring import (
    DeepSeekQuestionAuthoringProvider,
    ProviderQuestionSolution,
    ProviderQuestionDraft,
    QuestionAuthoring,
    QuestionAuthoringClarificationRequired,
    QuestionAuthoringContext,
    QuestionAuthoringError,
    QuestionAuthoringProviderError,
    QuestionAuthoringStatementPreview,
    QuestionAuthoringUnavailableError,
    QuestionDesignBrief,
    QuestionDraftEditableContent,
    QuestionDraftOption,
)
from app.modules.deepseek import DeepSeekJsonResponseError


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

    def regenerate_solution(self, current: ProviderQuestionDraft) -> ProviderQuestionSolution:
        return ProviderQuestionSolution(
            solution_method="重新组织的定义法",
            solution_steps=["先固定题面与答案。", "再给出不含试错过程的成稿推导。"],
            answer_value=current.answer_value,
            final_answer=current.final_answer,
        )


def passing_question_review(
    answer_value: str = "B",
    final_answer: str = "B",
) -> dict[str, object]:
    return {
        "passed": True,
        "summary": "题面条件相容、可解，已从题面独立求得答案。",
        "issues": [],
        "independent_answer_value": answer_value,
        "independent_final_answer": final_answer,
    }


def passing_completed_solution_review(
    answer_value: str = "B",
    final_answer: str = "B",
) -> dict[str, object]:
    return {
        "passed": True,
        "question_valid": True,
        "solution_valid": True,
        "answer_consistent": True,
        "summary": "题面、解析与标准答案一致。",
        "issues": [],
        "independent_answer_value": answer_value,
        "independent_final_answer": final_answer,
    }


def test_deepseek_provider_recovers_empty_non_choice_answer_value() -> None:
    core_payload = {
        "question_type": "open_response",
        "stem_plain": "已知椭圆的离心率与一个过点条件，求其标准方程。",
        "stem_latex": r"已知椭圆的离心率与一个过点条件，求其标准方程。",
        "options": [],
        "estimated_difficulty": 5,
    }
    plan_payload = {
        "solution_method": "利用离心率和过点条件建立方程组。",
        "sections": [
            {"order": 1, "title": "设元", "goal": "设出椭圆标准方程"},
            {"order": 2, "title": "求解", "goal": "代入条件求出参数"},
        ],
        "authoring_intent": "考查椭圆标准方程。",
        "curriculum_node_id": None,
        "knowledge_points": ["椭圆的标准方程"],
        "assessed_methods": ["待定系数法"],
        "common_mistakes": ["混淆焦距与半焦距"],
    }

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            if schema_name == "private_question_authoring_core":
                payload = core_payload
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review(
                    r"$\frac{x^2}{4}+\frac{y^2}{3}=1$",
                    r"$\frac{x^2}{4}+\frac{y^2}{3}=1$",
                )
            elif schema_name == "private_question_authoring_solution_plan":
                payload = plan_payload
            elif schema_name == "private_question_authoring_solution_conclusion":
                payload = {
                    "answer_value": r"$\frac{x^2}{4}+\frac{y^2}{3}=1$",
                    "final_answer": r"$\frac{x^2}{4}+\frac{y^2}{3}=1$",
                }
            elif schema_name == "private_question_authoring_completed_solution_review":
                payload = passing_completed_solution_review(
                    r"$\frac{x^2}{4}+\frac{y^2}{3}=1$",
                    r"$\frac{x^2}{4}+\frac{y^2}{3}=1$",
                )
            else:
                section = json.loads(str(kwargs["input_text"]))["section"]
                payload = {
                    "order": section["order"],
                    "steps": [f"{section['title']}：{section['goal']}。"],
                }
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(payload, ensure_ascii=False),
                            }
                        ],
                    }
                ]
            }

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="给我出一道圆锥曲线压轴题",
                grade="高三",
                question_type="open_response",
                target_difficulty=5,
            ),
            question_type="open_response",
            curriculum=None,
            curriculum_options=(),
        )
    )

    assert content.answer_value == r"$\frac{x^2}{4}+\frac{y^2}{3}=1$"
    assert content.final_answer == r"$\frac{x^2}{4}+\frac{y^2}{3}=1$"
    assert content.solution_steps == ["设元：设出椭圆标准方程。", "求解：代入条件求出参数。"]


def test_deepseek_provider_assembles_a_long_solution_from_bounded_sections() -> None:
    long_stem = "已知圆锥曲线综合条件，完成下列多问。" + "补充条件；" * 450
    long_step = "由 $x^2+y^2=1$ 结合题设逐项推导，保留必要的中文依据。" * 80
    calls: list[str] = []

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            calls.append(schema_name)
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "open_response",
                    "stem_plain": long_stem,
                    "stem_latex": long_stem,
                    "options": [],
                    "estimated_difficulty": 5,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review("三问结论", "三问结论依次为 $1$、$2$、$3$。")
            elif schema_name == "private_question_authoring_solution_plan":
                payload = {
                    "solution_method": "解析几何与代数运算综合法",
                    "sections": [
                        {"order": index, "title": f"第{index}问", "goal": f"完成第{index}问推导"}
                        for index in range(1, 5)
                    ],
                    "authoring_intent": "考查圆锥曲线综合推理。",
                    "curriculum_node_id": None,
                    "knowledge_points": ["圆锥曲线综合"],
                    "assessed_methods": ["设而不求"],
                    "common_mistakes": ["遗漏参数范围"],
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                payload = {
                    "answer_value": "三问结论依次为 $1$、$2$、$3$。",
                    "final_answer": "三问结论依次为 $1$、$2$、$3$。",
                }
            elif schema_name == "private_question_authoring_completed_solution_review":
                payload = passing_completed_solution_review(
                    "三问结论依次为 $1$、$2$、$3$。",
                    "三问结论依次为 $1$、$2$、$3$。",
                )
            else:
                section = json.loads(str(kwargs["input_text"]))["section"]
                payload = {
                    "order": section["order"],
                    "steps": [long_step, *[f"补充推导步骤 {index}。" for index in range(1, 14)]],
                }
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="生成一道包含多个小问和完整长解析的圆锥曲线压轴题",
                grade="高三",
                question_type="open_response",
                target_difficulty=5,
            ),
            question_type="open_response",
            curriculum=None,
            curriculum_options=(),
        )
    )

    assert len(content.stem_plain) > 1600
    assert sum(len(step) for step in content.solution_steps) > 6000
    assert len(content.solution_steps) == 56
    assert calls.count("private_question_authoring_core") == 1
    assert calls.count("private_question_authoring_solution_plan") == 1
    assert calls.count("private_question_authoring_solution_section") == 4


def test_deepseek_provider_reviews_and_repairs_an_impossible_question_before_solution() -> None:
    calls: list[str] = []
    progress: list[str] = []
    approved_statements: list[QuestionAuthoringStatementPreview] = []
    review_count = 0

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            nonlocal review_count
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            action = str(kwargs["action"])
            calls.append(action)
            if action == "辅助命题（core）":
                payload = {
                    "question_type": "single_choice",
                    "stem_plain": "在直角三角形 ABF₁ 中，AB⊥AF₁，AF₁=8，BF₁=6，求离心率。",
                    "stem_latex": "在直角三角形 $ABF_1$ 中，$AB\\perp AF_1$，$AF_1=8$，$BF_1=6$，求离心率。",
                    "options": [
                        {"key": "A", "text": "$\\frac{1}{2}$"},
                        {"key": "B", "text": "$\\frac{2}{3}$"},
                        {"key": "C", "text": "$\\frac{3}{4}$"},
                        {"key": "D", "text": "$\\frac{4}{5}$"},
                    ],
                    "estimated_difficulty": 4,
                }
            elif schema_name == "private_question_authoring_question_review":
                review_count += 1
                payload = (
                    {
                        "passed": False,
                        "summary": "直角三角形的斜边 BF₁=6 小于直角边 AF₁=8，题设无实数解。",
                        "issues": ["BF₁ 是斜边却短于 AF₁，几何条件矛盾。"],
                    }
                    if review_count == 1
                    else {
                        "passed": True,
                        "summary": "修订后斜边长于两条直角边，题面可解且选项包含唯一答案。",
                        "issues": [],
                        "independent_answer_value": "B",
                        "independent_final_answer": "B",
                    }
                )
            elif action == "辅助命题（core-question-repair）":
                payload = {
                    "question_type": "single_choice",
                    "stem_plain": "在直角三角形 ABF₁ 中，AB⊥AF₁，AF₁=8，BF₁=10，求 AB 的长。",
                    "stem_latex": "在直角三角形 $ABF_1$ 中，$AB\\perp AF_1$，$AF_1=8$，$BF_1=10$，求 $AB$ 的长。",
                    "options": [
                        {"key": "A", "text": "$4$"},
                        {"key": "B", "text": "$6$"},
                        {"key": "C", "text": "$8$"},
                        {"key": "D", "text": "$10$"},
                    ],
                    "estimated_difficulty": 2,
                }
            elif schema_name == "private_question_authoring_solution_plan":
                payload = {
                    "solution_method": "勾股定理",
                    "sections": [{"order": 1, "title": "计算", "goal": "利用勾股定理求边长"}],
                    "authoring_intent": "审核几何条件后考查勾股定理。",
                    "curriculum_node_id": None,
                    "knowledge_points": ["勾股定理"],
                    "assessed_methods": ["直接计算"],
                    "common_mistakes": ["误判斜边"],
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                payload = {"answer_value": "B", "final_answer": "B"}
            elif schema_name == "private_question_authoring_completed_solution_review":
                payload = passing_completed_solution_review()
            else:
                payload = {"order": 1, "steps": ["由勾股定理，$AB=\\sqrt{10^2-8^2}=6$，故选 B。"]}
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="命制一道结合圆锥曲线背景的三角形选择题",
                question_type="single_choice",
                target_difficulty=4,
            ),
            question_type="single_choice",
            curriculum=None,
            curriculum_options=(),
            on_progress=progress.append,
            on_statement_approved=approved_statements.append,
        )
    )

    assert "BF₁=10" in content.stem_plain
    assert "BF₁=6" not in content.stem_plain
    assert content.answer_value == "B"
    assert content.solution_status == "ready"
    assert len(approved_statements) == 1
    assert approved_statements[0].stem_plain == content.stem_plain
    assert approved_statements[0].options == content.options
    assert progress == [
        "composing",
        "reviewing",
        "refining",
        "solving",
        "reviewing_solution",
    ]
    assert calls == [
        "辅助命题（core）",
        "辅助命题（question-review）",
        "辅助命题（core-question-repair）",
        "辅助命题（core-question-repair-review-check）",
        "辅助命题（solution-plan）",
        "辅助命题（solution-section-1）",
        "辅助命题（solution-conclusion）",
        "辅助命题（completed-solution-review）",
    ]


def test_deepseek_provider_stops_before_solution_when_repaired_question_still_fails_review() -> None:
    calls: list[str] = []

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            action = str(kwargs["action"])
            calls.append(action)
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "single_choice",
                    "stem_plain": "在直角三角形中，斜边长 6，一条直角边长 8，求另一条直角边。",
                    "stem_latex": "在直角三角形中，斜边长 $6$，一条直角边长 $8$，求另一条直角边。",
                    "options": [
                        {"key": "A", "text": "$2$"},
                        {"key": "B", "text": "$4$"},
                        {"key": "C", "text": "$6$"},
                        {"key": "D", "text": "$10$"},
                    ],
                    "estimated_difficulty": 3,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = {
                    "passed": False,
                    "summary": "斜边短于直角边，题面矛盾。",
                    "issues": ["斜边长 6 小于直角边长 8。"],
                }
            elif action.startswith("辅助命题（core-question-repair"):
                payload = {
                    "question_type": "single_choice",
                    "stem_plain": "在直角三角形中，斜边长 6，一条直角边长 8，求另一条直角边。",
                    "stem_latex": "在直角三角形中，斜边长 $6$，一条直角边长 $8$，求另一条直角边。",
                    "options": [
                        {"key": "A", "text": "$2$"},
                        {"key": "B", "text": "$4$"},
                        {"key": "C", "text": "$6$"},
                        {"key": "D", "text": "$10$"},
                    ],
                    "estimated_difficulty": 3,
                }
            else:
                pytest.fail(f"题面未通过自审核时不应进入解析阶段：{action}")
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    with pytest.raises(QuestionAuthoringProviderError, match="多份候选题均未通过闭环审核"):
        provider.generate(
            QuestionAuthoringContext(
                brief=QuestionDesignBrief(
                    request_text="命制一道直角三角形选择题",
                    question_type="single_choice",
                    target_difficulty=3,
                ),
                question_type="single_choice",
                curriculum=None,
                curriculum_options=(),
            )
        )

    expected_candidate_calls = [
        "辅助命题（core）",
        "辅助命题（question-review）",
        "辅助命题（core-question-repair）",
        "辅助命题（core-question-repair-review-check）",
        "辅助命题（core-question-repair-2）",
        "辅助命题（core-question-repair-review-check-2）",
        "辅助命题（core-question-repair-3）",
        "辅助命题（core-question-repair-review-check-3）",
    ]
    assert calls == expected_candidate_calls * 3


def test_deepseek_provider_repairs_and_reaudits_statement_when_full_solve_exposes_a_flaw() -> None:
    progress: list[str] = []
    approved_statements: list[QuestionAuthoringStatementPreview] = []
    question_review_count = 0
    conclusion_count = 0
    completed_review_count = 0

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            nonlocal question_review_count, conclusion_count, completed_review_count
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            action = str(kwargs["action"])
            input_value = json.loads(str(kwargs["input_text"]))
            if action == "辅助命题（core）":
                payload = {
                    "question_type": "fill_blank",
                    "stem_plain": "关于 x 的方程 x²+1=0 的实数根个数为______。",
                    "stem_latex": "关于 $x$ 的方程 $x^2+1=0$ 的实数根个数为 $\\_\\_\\_\\_$。",
                    "options": [],
                    "estimated_difficulty": 5,
                }
            elif action == "辅助命题（post-solution-question-repair）":
                payload = {
                    "question_type": "fill_blank",
                    "stem_plain": "关于 x 的方程 x²-1=0 的实数根个数为______。",
                    "stem_latex": "关于 $x$ 的方程 $x^2-1=0$ 的实数根个数为 $\\_\\_\\_\\_$。",
                    "options": [],
                    "estimated_difficulty": 5,
                }
            elif schema_name == "private_question_authoring_question_review":
                question_review_count += 1
                expected = "1" if question_review_count == 1 else "2"
                payload = passing_question_review(expected, expected)
                if question_review_count == 1:
                    payload["summary"] = "复杂题面审核摘要。" * 80
            elif schema_name == "private_question_authoring_solution_plan":
                payload = {
                    "solution_method": "方程求解",
                    "sections": [{"order": 1, "title": "求根", "goal": "求解并核对根的个数"}],
                    "authoring_intent": "考查实数根与方程求解。",
                    "curriculum_node_id": None,
                    "knowledge_points": ["方程的根"],
                    "assessed_methods": ["直接求解"],
                    "common_mistakes": ["忽略实数范围"],
                }
            elif schema_name == "private_question_authoring_solution_section":
                statement = input_value["question_statement"]["stem_plain"]
                payload = {
                    "order": 1,
                    "steps": (
                        ["因为 $x^2=-1$ 在实数范围内无解，所以实数根个数为 $0$。"]
                        if "x²+1" in statement
                        else ["由 $x^2-1=0$ 得 $x=\\pm1$，所以实数根个数为 $2$。"]
                    ),
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                conclusion_count += 1
                expected = "0" if conclusion_count == 1 else "2"
                payload = {"answer_value": expected, "final_answer": expected}
            elif schema_name == "private_question_authoring_completed_solution_review":
                completed_review_count += 1
                payload = (
                    {
                        "passed": True,
                        "question_valid": False,
                        "solution_valid": True,
                        "answer_consistent": True,
                        "summary": "完整求解表明题面与预期的命题目标冲突。",
                        "issues": ["方程在实数范围内无根，题面必须修改。"],
                        "independent_answer_value": "0",
                        "independent_final_answer": "0",
                    }
                    if completed_review_count == 1
                    else passing_completed_solution_review("2", "2")
                )
            else:  # pragma: no cover - protects the staged contract
                pytest.fail(f"unexpected stage: {action}")
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="来一道能作为填空压轴题的导数计算题",
                grade="高三",
                question_type="fill_blank",
                target_difficulty=5,
                teaching_purpose="考试压轴",
                additional_constraints="一定要难，要有压轴题的水平",
            ),
            question_type="fill_blank",
            curriculum=None,
            curriculum_options=(),
            on_progress=progress.append,
            on_statement_approved=approved_statements.append,
        )
    )

    assert "x²-1=0" in content.stem_plain
    assert content.answer_value == "2"
    assert content.final_answer == "2"
    assert [statement.stem_plain for statement in approved_statements] == [
        "关于 x 的方程 x²+1=0 的实数根个数为______。",
        "关于 x 的方程 x²-1=0 的实数根个数为______。",
    ]
    assert progress == [
        "composing",
        "reviewing",
        "solving",
        "reviewing_solution",
        "refining",
        "solving",
        "reviewing_solution",
    ]
    assert question_review_count == 2
    assert completed_review_count == 2


def test_deepseek_provider_rewrites_deliberative_solution_before_returning() -> None:
    calls: Counter[str] = Counter()

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            calls[schema_name] += 1
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "open_response",
                    "stem_plain": "已知双曲线条件，完成证明并求参数范围。",
                    "stem_latex": "已知双曲线条件，完成证明并求参数范围。",
                    "options": [],
                    "estimated_difficulty": 5,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review(
                    "参数范围为 $(-\\infty,-1)\\cup(1,+\\infty)$。",
                    "参数范围为 $(-\\infty,-1)\\cup(1,+\\infty)$。",
                )
            elif schema_name == "private_question_authoring_solution_plan":
                payload = {
                    "solution_method": "解析几何法",
                    "sections": [{"order": 1, "title": "求范围", "goal": "完成参数范围推导"}],
                    "authoring_intent": "考查双曲线综合推理。",
                    "curriculum_node_id": None,
                    "knowledge_points": [],
                    "assessed_methods": [],
                    "common_mistakes": [],
                }
            elif schema_name == "private_question_authoring_solution_cleanup":
                payload = {
                    "order": 1,
                    "steps": ["由判别式大于零，解得参数范围为 $(-\\infty,-1)\\cup(1,+\\infty)$。"],
                    "mathematically_valid": True,
                    "issue_summary": None,
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                payload = {
                    "answer_value": "参数范围为 $(-\\infty,-1)\\cup(1,+\\infty)$。",
                    "final_answer": "参数范围为 $(-\\infty,-1)\\cup(1,+\\infty)$。",
                }
            elif schema_name == "private_question_authoring_completed_solution_review":
                payload = passing_completed_solution_review(
                    "参数范围为 $(-\\infty,-1)\\cup(1,+\\infty)$。",
                    "参数范围为 $(-\\infty,-1)\\cup(1,+\\infty)$。",
                )
            else:
                payload = {
                    "order": 1,
                    "steps": [
                        "让我们重新审视前面的计算。我们可能算错了，先回退并重新推导。",
                        "最终得到参数范围。",
                    ],
                }
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="生成一道双曲线综合题",
                question_type="open_response",
                target_difficulty=5,
            ),
            question_type="open_response",
            curriculum=None,
            curriculum_options=(),
        )
    )

    assert content.solution_steps == [
        "由判别式大于零，解得参数范围为 $(-\\infty,-1)\\cup(1,+\\infty)$。"
    ]
    assert calls["private_question_authoring_solution_section"] == 1
    assert calls["private_question_authoring_solution_cleanup"] == 1


def test_deepseek_provider_regenerates_solution_when_cleanup_blames_derivation() -> None:
    section_attempt = 0

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            nonlocal section_attempt
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "single_choice",
                    "stem_plain": "某校组织投币闯关活动，结合数列递推关系判断第 n 轮获胜概率。",
                    "stem_latex": "某校组织投币闯关活动，结合数列递推关系判断第 $n$ 轮获胜概率。",
                    "options": [
                        {"key": "A", "text": "$\\frac{1}{3}$"},
                        {"key": "B", "text": "$\\frac{2}{3}$"},
                        {"key": "C", "text": "$\\frac{3}{4}$"},
                        {"key": "D", "text": "$1$"},
                    ],
                    "estimated_difficulty": 5,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review()
            elif schema_name == "private_question_authoring_solution_plan":
                payload = {
                    "solution_method": "建立数列递推并求事件概率。",
                    "sections": [{"order": 1, "title": "列递推", "goal": "求出第 n 轮获胜概率"}],
                    "authoring_intent": "综合考查数列递推与概率模型。",
                    "curriculum_node_id": None,
                    "knowledge_points": ["数列递推", "概率模型"],
                    "assessed_methods": ["建立递推关系"],
                    "common_mistakes": ["忽略概率和为 1"],
                }
            elif schema_name == "private_question_authoring_solution_cleanup":
                payload = {
                    "order": 1,
                    "steps": ["当前推导发现题面条件无法同时成立，请教师独立核验。"],
                    "mathematically_valid": False,
                    "issue_summary": "当前解析错误地建立了递推关系。",
                    "fault_source": "solution",
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                payload = {"answer_value": "B", "final_answer": "B"}
            elif schema_name == "private_question_authoring_completed_solution_review":
                payload = passing_completed_solution_review("B", "B")
            else:
                section_attempt += 1
                payload = (
                    {
                        "order": 1,
                        "steps": [
                            "重新核对初始条件后发现与题设不符，说明题面有误，无法选出正确答案。"
                        ],
                    }
                    if section_attempt == 1
                    else {"order": 1, "steps": ["建立正确递推关系后，计算得到选项 B。"]}
                )
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="命制一道数列与概率结合的复杂选择题",
                question_type="single_choice",
                target_difficulty=5,
            ),
            question_type="single_choice",
            curriculum=None,
            curriculum_options=(),
        )
    )

    assert section_attempt == 2
    assert content.answer_value == "B"
    assert content.solution_steps == ["建立正确递推关系后，计算得到选项 B。"]


def test_deepseek_provider_uses_answer_derived_after_solution_not_core_guess() -> None:
    """The authored standard answer must follow the completed derivation, not a core-stage guess."""

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "single_choice",
                    "stem_plain": "已知条件可推出函数恒为 1，判断其满足的不等式解集。",
                    "stem_latex": "已知条件可推出函数恒为 $1$，判断其满足的不等式解集。",
                    "options": [
                        {"key": "A", "text": "$(0,e]$"},
                        {"key": "B", "text": "$[e,+\\infty)$"},
                        {"key": "C", "text": "$(0,1]\\cup[e,+\\infty)$"},
                        {"key": "D", "text": "$[1,e]$"},
                    ],
                    "estimated_difficulty": 4,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review("A", "A")
            elif schema_name == "private_question_authoring_solution_plan":
                payload = {
                    "solution_method": "先求函数，再解不等式。",
                    "sections": [{"order": 1, "title": "求解", "goal": "完成推导并判断选项"}],
                    "authoring_intent": "考查函数与不等式。",
                    "curriculum_node_id": None,
                    "knowledge_points": ["函数与不等式"],
                    "assessed_methods": ["等价转化"],
                    "common_mistakes": ["直接沿用暂定答案"],
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                payload = {"answer_value": "A", "final_answer": "A"}
            elif schema_name == "private_question_authoring_completed_solution_review":
                payload = passing_completed_solution_review("A", "A")
            else:
                payload = {
                    "order": 1,
                    "steps": ["由题设解得 $f(x)=1$，不等式等价于 $x\\le e$；结合 $x>0$，解集为 $(0,e]$，对应选项 A。"],
                }
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="命制一道函数与不等式单选题",
                question_type="single_choice",
                target_difficulty=4,
            ),
            question_type="single_choice",
            curriculum=None,
            curriculum_options=(),
        )
    )

    assert content.answer_value == "A"
    assert content.final_answer == "A"
    assert content.solution_status == "ready"
    assert "对应选项 A" in content.solution_steps[-1]


def test_deepseek_provider_regenerates_solution_when_final_audit_blames_solution() -> None:
    """A valid statement must survive a bad solution and still become a complete draft."""

    progress: list[str] = []
    solution_attempt = 0
    completed_review_count = 0

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            nonlocal solution_attempt, completed_review_count
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            action = str(kwargs["action"])
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "single_choice",
                    "stem_plain": "若 x=1，则下列结论正确的是（ ）。",
                    "stem_latex": "若 $x=1$，则下列结论正确的是（ ）。",
                    "options": [
                        {"key": "A", "text": "$x=1$"},
                        {"key": "B", "text": "$x=2$"},
                        {"key": "C", "text": "$x=3$"},
                        {"key": "D", "text": "$x=4$"},
                    ],
                    "estimated_difficulty": 1,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review("A", "A")
            elif schema_name == "private_question_authoring_solution_plan":
                solution_attempt += 1
                payload = {
                    "solution_method": "直接判断",
                    "sections": [{"order": 1, "title": "判断", "goal": "由题设判断选项"}],
                    "authoring_intent": "验证解析错误后的自动恢复。",
                    "curriculum_node_id": None,
                    "knowledge_points": [],
                    "assessed_methods": [],
                    "common_mistakes": [],
                }
            elif schema_name == "private_question_authoring_solution_section":
                payload = {
                    "order": 1,
                    "steps": (
                        ["错误地把 $x=1$ 看成 $x=2$，故选 B。"]
                        if solution_attempt == 1
                        else ["由题设直接得到 $x=1$，故选 A。"]
                    ),
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                answer = "B" if solution_attempt == 1 else "A"
                payload = {"answer_value": answer, "final_answer": answer}
            elif schema_name == "private_question_authoring_completed_solution_review":
                completed_review_count += 1
                payload = (
                    {
                        "passed": False,
                        "question_valid": True,
                        "solution_valid": False,
                        "answer_consistent": False,
                        "summary": "题面成立，错误来自解析。",
                        "issues": ["解析把题设 x=1 错读为 x=2。"],
                        "independent_answer_value": "A",
                        "independent_final_answer": "A",
                    }
                    if completed_review_count == 1
                    else passing_completed_solution_review("A", "A")
                )
            else:  # pragma: no cover - staged-contract guard
                pytest.fail(f"unexpected stage: {action}")
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="命制一道单项选择题",
                question_type="single_choice",
            ),
            question_type="single_choice",
            curriculum=None,
            curriculum_options=(),
            on_progress=progress.append,
        )
    )

    assert content.stem_plain == "若 x=1，则下列结论正确的是（ ）。"
    assert content.answer_value == "A"
    assert content.final_answer == "A"
    assert content.solution_steps == ["由题设直接得到 $x=1$，故选 A。"]
    assert solution_attempt == 2
    assert completed_review_count == 2
    assert progress == [
        "composing",
        "reviewing",
        "solving",
        "reviewing_solution",
        "regenerating_solution",
        "reviewing_solution",
    ]


def test_deepseek_provider_recovers_when_failed_final_audit_omits_independent_answers() -> None:
    """A failed audit may omit answers; that must trigger recovery, not schema failure."""

    solution_attempt = 0
    completed_review_count = 0

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            nonlocal solution_attempt, completed_review_count
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "fill_blank",
                    "stem_plain": "若 x=1，则 x+1=____。",
                    "stem_latex": "若 $x=1$，则 $x+1=\\underline{\\qquad}$。",
                    "options": [],
                    "estimated_difficulty": 1,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review("2", "2")
            elif schema_name == "private_question_authoring_solution_plan":
                solution_attempt += 1
                payload = {
                    "solution_method": "代入计算",
                    "sections": [{"order": 1, "title": "计算", "goal": "代入求值"}],
                    "authoring_intent": "验证审核缺字段后的闭环恢复。",
                    "curriculum_node_id": None,
                    "knowledge_points": [],
                    "assessed_methods": [],
                    "common_mistakes": [],
                }
            elif schema_name == "private_question_authoring_solution_section":
                payload = {
                    "order": 1,
                    "steps": (
                        ["错误计算得到 $x+1=3$。"]
                        if solution_attempt == 1
                        else ["代入 $x=1$，得到 $x+1=2$。"]
                    ),
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                answer = "3" if solution_attempt == 1 else "2"
                payload = {"answer_value": answer, "final_answer": answer}
            elif schema_name == "private_question_authoring_completed_solution_review":
                completed_review_count += 1
                payload = (
                    {
                        "passed": False,
                        "question_valid": True,
                        "solution_valid": False,
                        "answer_consistent": False,
                        "summary": "题面成立，但标准答案错误。",
                        "issues": ["解析计算错误，标准答案错误。"],
                    }
                    if completed_review_count == 1
                    else passing_completed_solution_review("2", "2")
                )
            else:  # pragma: no cover - staged-contract guard
                pytest.fail(f"unexpected stage: {schema_name}")
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="来一道能作为填空压轴题的导数计算题",
                grade="高三",
                question_type="fill_blank",
                target_difficulty=5,
                teaching_purpose="考试压轴",
                additional_constraints="一定要难，要有压轴题的水平",
            ),
            question_type="fill_blank",
            curriculum=None,
            curriculum_options=(),
        )
    )

    assert content.answer_value == "2"
    assert content.final_answer == "2"
    assert content.solution_status == "ready"
    assert solution_attempt == 2
    assert completed_review_count == 2


def test_deepseek_provider_reauthors_whole_question_after_solution_recovery_is_exhausted() -> None:
    """Content-quality exhaustion must restart from a new statement, not fail the task."""

    core_count = 0
    solution_count = 0

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            nonlocal core_count, solution_count
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            if schema_name == "private_question_authoring_core":
                core_count += 1
                payload = {
                    "question_type": "fill_blank",
                    "stem_plain": (
                        "第一份候选题：若 x=1，则 x+1=____。"
                        if core_count == 1
                        else "第二份候选题：若 x=2，则 x+1=____。"
                    ),
                    "stem_latex": (
                        "第一份候选题：若 $x=1$，则 $x+1=\\underline{\\qquad}$。"
                        if core_count == 1
                        else "第二份候选题：若 $x=2$，则 $x+1=\\underline{\\qquad}$。"
                    ),
                    "options": [],
                    "estimated_difficulty": 1,
                }
            elif schema_name == "private_question_authoring_question_review":
                expected = "2" if core_count == 1 else "3"
                payload = passing_question_review(expected, expected)
            elif schema_name == "private_question_authoring_solution_plan":
                solution_count += 1
                payload = {
                    "solution_method": "代入计算",
                    "sections": [{"order": 1, "title": "计算", "goal": "代入求值"}],
                    "authoring_intent": "验证整题自动重命制。",
                    "curriculum_node_id": None,
                    "knowledge_points": [],
                    "assessed_methods": [],
                    "common_mistakes": [],
                }
            elif schema_name == "private_question_authoring_solution_section":
                payload = {
                    "order": 1,
                    "steps": [
                        "无法形成正确解析。"
                        if core_count == 1
                        else "代入 $x=2$，得到 $x+1=3$。"
                    ],
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                answer = "错误" if core_count == 1 else "3"
                payload = {"answer_value": answer, "final_answer": answer}
            elif schema_name == "private_question_authoring_completed_solution_review":
                payload = (
                    {
                        "passed": False,
                        "question_valid": True,
                        "solution_valid": False,
                        "answer_consistent": False,
                        "summary": "题面成立，但解析不合格。",
                        "issues": ["解析没有正确完成计算。"],
                        "independent_answer_value": "2",
                        "independent_final_answer": "2",
                    }
                    if core_count == 1
                    else passing_completed_solution_review("3", "3")
                )
            else:  # pragma: no cover - staged-contract guard
                pytest.fail(f"unexpected stage: {schema_name}")
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="来一道能作为填空压轴题的导数计算题",
                question_type="fill_blank",
                target_difficulty=5,
            ),
            question_type="fill_blank",
            curriculum=None,
            curriculum_options=(),
        )
    )

    assert content.stem_plain.startswith("第二份候选题")
    assert content.answer_value == "3"
    assert content.final_answer == "3"
    assert content.solution_status == "ready"
    assert core_count == 2
    assert solution_count == 5  # four failed solves for candidate one, then success


def test_deepseek_provider_uses_final_audit_to_resolve_an_incorrect_initial_review() -> None:
    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "single_choice",
                    "stem_plain": "若 x=1，则下列结论正确的是（ ）。",
                    "stem_latex": "若 $x=1$，则下列结论正确的是（ ）。",
                    "options": [
                        {"key": "A", "text": "$x=1$"},
                        {"key": "B", "text": "$x=2$"},
                        {"key": "C", "text": "$x=3$"},
                        {"key": "D", "text": "$x=4$"},
                    ],
                    "estimated_difficulty": 1,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review("B", "B")
            elif schema_name == "private_question_authoring_solution_plan":
                payload = {
                    "solution_method": "直接判断",
                    "sections": [{"order": 1, "title": "判断", "goal": "由题设确定选项"}],
                    "authoring_intent": "验证独立答案交叉核验。",
                    "curriculum_node_id": None,
                    "knowledge_points": [],
                    "assessed_methods": [],
                    "common_mistakes": [],
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                payload = {"answer_value": "A", "final_answer": "A"}
            elif schema_name == "private_question_authoring_completed_solution_review":
                payload = passing_completed_solution_review("A", "A")
            else:
                payload = {"order": 1, "steps": ["由题设直接得到 $x=1$，故选 A。"]}
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="命制一道简单单选题用于交叉核验",
                question_type="single_choice",
                target_difficulty=1,
            ),
            question_type="single_choice",
            curriculum=None,
            curriculum_options=(),
        )
    )

    assert content.answer_value == "A"
    assert content.final_answer == "A"
    assert content.solution_steps == ["由题设直接得到 $x=1$，故选 A。"]


def test_deepseek_provider_does_not_publish_answer_when_solution_stage_fails() -> None:
    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "open_response",
                    "stem_plain": "已知数列满足递推关系，求其通项并证明所得结论。",
                    "stem_latex": "已知数列满足递推关系，求其通项并证明所得结论。",
                    "options": [],
                    "estimated_difficulty": 5,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review()
            else:
                payload = {}
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    with pytest.raises(QuestionAuthoringProviderError, match="不完整的结构化内容"):
        provider.generate(
            QuestionAuthoringContext(
                brief=QuestionDesignBrief(
                    request_text="命制一道复杂数列解答题",
                    question_type="open_response",
                    target_difficulty=5,
                ),
                question_type="open_response",
                curriculum=None,
                curriculum_options=(),
            )
        )


def test_deepseek_provider_retries_only_the_failed_solution_section() -> None:
    attempts: Counter[int] = Counter()
    lock = Lock()

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "open_response",
                    "stem_plain": "已知椭圆条件，完成两问并给出完整证明。",
                    "stem_latex": "已知椭圆条件，完成两问并给出完整证明。",
                    "options": [],
                    "estimated_difficulty": 5,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review()
            elif schema_name == "private_question_authoring_solution_plan":
                payload = {
                    "solution_method": "解析几何法",
                    "sections": [
                        {"order": 1, "title": "第一问", "goal": "完成第一问"},
                        {"order": 2, "title": "第二问", "goal": "完成第二问"},
                        {"order": 3, "title": "总结", "goal": "整理最终结论"},
                    ],
                    "authoring_intent": "综合考查。",
                    "curriculum_node_id": None,
                    "knowledge_points": [],
                    "assessed_methods": [],
                    "common_mistakes": [],
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                payload = {"answer_value": "最终结论", "final_answer": "最终结论"}
            elif schema_name == "private_question_authoring_completed_solution_review":
                payload = passing_completed_solution_review("最终结论", "最终结论")
            else:
                section = json.loads(str(kwargs["input_text"]))["section"]
                order = int(section["order"])
                with lock:
                    attempts[order] += 1
                    current_attempt = attempts[order]
                if order == 2 and current_attempt == 1:
                    raise DeepSeekJsonResponseError("第二段 JSON 截断")
                payload = {"order": order, "steps": [f"第{order}段完整解析。"]}
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="生成一道圆锥曲线长解析题",
                question_type="open_response",
                target_difficulty=5,
            ),
            question_type="open_response",
            curriculum=None,
            curriculum_options=(),
        )
    )

    assert content.solution_steps == ["第1段完整解析。", "第2段完整解析。", "第3段完整解析。"]
    assert attempts == Counter({2: 2, 1: 1, 3: 1})


def test_deepseek_provider_subdivides_only_a_persistently_truncated_section() -> None:
    calls: Counter[str] = Counter()

    class FakeDeepSeekClient:
        def request(self, **kwargs: object) -> dict:
            schema_name = kwargs["output_schema"]["name"]  # type: ignore[index]
            calls[schema_name] += 1
            input_value = json.loads(str(kwargs["input_text"]))
            if schema_name == "private_question_authoring_core":
                payload = {
                    "question_type": "open_response",
                    "stem_plain": "一道需要完整长解析的圆锥曲线综合题。",
                    "stem_latex": "一道需要完整长解析的圆锥曲线综合题。",
                    "options": [],
                    "estimated_difficulty": 5,
                }
            elif schema_name == "private_question_authoring_question_review":
                payload = passing_question_review()
            elif schema_name == "private_question_authoring_solution_plan":
                payload = {
                    "solution_method": "解析几何法",
                    "sections": [{"order": 1, "title": "长推导", "goal": "完成全部推导"}],
                    "authoring_intent": "综合考查。",
                    "curriculum_node_id": None,
                    "knowledge_points": [],
                    "assessed_methods": [],
                    "common_mistakes": [],
                }
            elif schema_name == "private_question_authoring_solution_conclusion":
                payload = {"answer_value": "最终结论", "final_answer": "最终结论"}
            elif schema_name == "private_question_authoring_completed_solution_review":
                payload = passing_completed_solution_review("最终结论", "最终结论")
            elif schema_name == "private_question_authoring_solution_subplan":
                payload = {
                    "parts": [
                        {"order": 1, "title": "前半段", "goal": "建立关系"},
                        {"order": 2, "title": "后半段", "goal": "求解并核对"},
                    ]
                }
            elif "parent_section" not in input_value:
                raise DeepSeekJsonResponseError("当前段持续截断")
            else:
                part = input_value["section"]
                payload = {"order": part["order"], "steps": [f"{part['title']}完整解析。"]}
            text = json.dumps(payload, ensure_ascii=False)
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}

    provider = DeepSeekQuestionAuthoringProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider.client = FakeDeepSeekClient()  # type: ignore[assignment]

    content = provider.generate(
        QuestionAuthoringContext(
            brief=QuestionDesignBrief(
                request_text="生成一道需要完整长解析的圆锥曲线综合题",
                question_type="open_response",
                target_difficulty=5,
            ),
            question_type="open_response",
            curriculum=None,
            curriculum_options=(),
        )
    )

    assert content.solution_steps == ["前半段完整解析。", "后半段完整解析。"]
    assert calls["private_question_authoring_core"] == 1
    assert calls["private_question_authoring_solution_plan"] == 1
    assert calls["private_question_authoring_solution_section"] == 4
    assert calls["private_question_authoring_solution_subplan"] == 1


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


def test_create_draft_refuses_to_return_a_solution_conflict_as_a_user_draft() -> None:
    class ConflictProvider(FakeProvider):
        def generate(self, context: QuestionAuthoringContext) -> ProviderQuestionDraft:
            return super().generate(context).model_copy(
                update={
                    "solution_method": "解析待教师核验",
                    "solution_steps": [
                        "解析未通过一致性检查，请教师根据完整题面自行核验，或重新生成解析。"
                    ],
                    "solution_status": "needs_teacher_verification",
                    "solution_issue": "解析推导与标准答案存在冲突。",
                }
            )

    authoring = QuestionAuthoring(
        curriculum=curriculum(),
        provider=ConflictProvider(),
        math_verifier=MathVerifier(),
    )

    with pytest.raises(QuestionAuthoringUnavailableError, match="不会返回半成品"):
        authoring.create_draft(
            QuestionDesignBrief(
                request_text="命制一道完整但解析可能需要复核的函数题。",
                question_type="single_choice",
            )
        )


def test_create_draft_keeps_choice_options_out_of_both_readable_stems() -> None:
    class EmbeddedOptionsProvider(FakeProvider):
        def generate(self, context: QuestionAuthoringContext) -> ProviderQuestionDraft:
            content = super().generate(context)
            return content.model_copy(
                update={
                    "stem_plain": (
                        "已知函数 f(x)=x²，判断其在实数范围内的单调性。"
                        "\\nA. 在定义域上恒增\\nB. 先减后增"
                        "\\nC. 在定义域上恒减\\nD. 不是函数"
                    ),
                    "stem_latex": (
                        r"已知函数 $f(x)=x^2$，判断其在实数范围内的单调性。"
                        r"\nA. 在定义域上恒增\nB. 先减后增"
                        r"\nC. 在定义域上恒减\nD. 不是函数"
                    ),
                }
            )

    draft = QuestionAuthoring(
        curriculum=curriculum(),
        provider=EmbeddedOptionsProvider(),
        math_verifier=MathVerifier(),
    ).create_draft(
        QuestionDesignBrief(
            request_text="命制一道函数单调性的完整单项选择题。",
            question_type="single_choice",
        )
    )

    assert draft.stem_plain == "已知函数 f(x)=x²，判断其在实数范围内的单调性。"
    assert draft.stem_latex == r"已知函数 $f(x)=x^2$，判断其在实数范围内的单调性。"
    assert [option.key for option in draft.options] == ["A", "B", "C", "D"]


def test_create_draft_rejects_generated_university_only_content() -> None:
    class UniversityScopeProvider(FakeProvider):
        def generate(self, context: QuestionAuthoringContext) -> ProviderQuestionDraft:
            return super().generate(context).model_copy(
                update={
                    "stem_plain": "设随机过程构成马尔可夫链，求其平稳分布。",
                    "stem_latex": "设随机过程构成马尔可夫链，求其平稳分布。",
                }
            )

    authoring = QuestionAuthoring(
        curriculum=curriculum(),
        provider=UniversityScopeProvider(),
        math_verifier=MathVerifier(),
    )

    with pytest.raises(QuestionAuthoringError, match="超出高中数学范围"):
        authoring.create_draft(
            QuestionDesignBrief(
                request_text="命制一道有背景的概率综合题。",
                question_type="single_choice",
            )
        )


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


def test_regenerate_solution_keeps_question_but_uses_newly_derived_answer() -> None:
    class ReansweringProvider(FakeProvider):
        def regenerate_solution(
            self, current: ProviderQuestionDraft
        ) -> ProviderQuestionSolution:
            return ProviderQuestionSolution(
                solution_method="重新组织的定义法",
                solution_steps=["只依据题面重新求解。", "完整推导得到选项 A。"],
                answer_value="A",
                final_answer="答案为 A。",
            )

    provider = ReansweringProvider()
    authoring = QuestionAuthoring(
        curriculum=curriculum(), provider=provider, math_verifier=MathVerifier()
    )
    draft = authoring.create_draft(
        QuestionDesignBrief(
            request_text="命制一道函数单调性的单选题。",
            curriculum_node_id="kp_monotonicity",
            question_type="single_choice",
            target_difficulty=2,
        )
    )

    regenerated = authoring.regenerate_solution(draft)

    assert regenerated.draft_id == draft.draft_id
    assert regenerated.stem_plain == draft.stem_plain
    assert regenerated.stem_latex == draft.stem_latex
    assert regenerated.options == draft.options
    assert regenerated.answer_value == "A"
    assert regenerated.final_answer == "答案为 A。"
    assert regenerated.authoring_intent == draft.authoring_intent
    assert regenerated.curriculum == draft.curriculum
    assert regenerated.solution_method == "重新组织的定义法"
    assert regenerated.solution_steps == ["只依据题面重新求解。", "完整推导得到选项 A。"]
    assert regenerated.visibility == "owner_only"
    assert regenerated.saved is False
    assert regenerated.verification.teacher_review_required is True
    assert any("重新推导" in warning for warning in regenerated.warnings)


def test_regenerate_solution_refuses_to_return_a_conflicting_half_result() -> None:
    class ConflictRegenerationProvider(FakeProvider):
        def regenerate_solution(
            self, current: ProviderQuestionDraft
        ) -> ProviderQuestionSolution:
            return ProviderQuestionSolution(
                solution_method="解析待教师核验",
                solution_steps=[
                    "解析未通过一致性检查，请教师根据完整题面自行核验，或再次重新生成解析。"
                ],
                answer_value=current.answer_value,
                final_answer=current.final_answer,
                solution_status="needs_teacher_verification",
                solution_issue="新解析仍与标准答案存在冲突。",
            )

    provider = ConflictRegenerationProvider()
    authoring = QuestionAuthoring(
        curriculum=curriculum(), provider=provider, math_verifier=MathVerifier()
    )
    draft = authoring.create_draft(
        QuestionDesignBrief(
            request_text="命制一道函数单调性的单选题。",
            question_type="single_choice",
        )
    )

    with pytest.raises(QuestionAuthoringUnavailableError, match="不会返回半成品"):
        authoring.regenerate_solution(draft)


def test_non_choice_draft_has_one_canonical_final_answer() -> None:
    authoring = QuestionAuthoring(
        curriculum=curriculum(),
        provider=FakeProvider(
            question_type="fill_blank",
            answer_value="√3/2 ≤ d ≤ 1",
            final_answer="d = 2√5/5",
        ),
        math_verifier=MathVerifier(),
    )

    draft = authoring.create_draft(
        QuestionDesignBrief(
            request_text="命制一道圆锥曲线填空题。",
            curriculum_node_id="kp_ellipse_geometry",
            question_type="fill_blank",
        )
    )

    assert draft.answer_value == "d = 2√5/5"
    assert draft.final_answer == "d = 2√5/5"
    checks = {item.code: item for item in draft.verification.checks}
    assert checks["answer_solution_consistency"].status == "passed"


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
    for provider, _failed_code in cases:
        authoring = QuestionAuthoring(
            curriculum=curriculum(),
            provider=provider,
            math_verifier=MathVerifier(),
        )
        with pytest.raises(QuestionAuthoringUnavailableError, match="不会把半成品交给教师"):
            authoring.create_draft(brief)


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
