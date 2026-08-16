"""Generate commercial-safe synthetic question-bank test fixtures.

This script is the single source of truth for the synthetic fixture family used
by the backend test suite after the Commercial V1 clean snapshot. Every
question, option, answer and solution in the generated files is created by this
project (source=project_created, synthetic=true). No third-party question
content, no exam-text copies, no private teacher material and no local machine
paths are present.

The fixtures reproduce the *workflow contracts* asserted by the migrated test
suite (import counts, curation counts, verifier canonical values, work queues,
publication gates) while replacing every stem/option/solution with simple
project-created mathematics.

Usage (from repository root, with backend venv active):
    python scripts/generate_synthetic_test_fixtures.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.modules.math_verifier import MathVerifier  # noqa: E402
from app.modules.question_bank import QuestionBank  # noqa: E402
from app.modules.question_variants import (  # noqa: E402
    LocalDiagnosticVariantProvider,
    QuestionVariantService,
    QuestionVariantGenerationRequest,
    TeacherVariantDraftCommand,
)

FIXTURE_ROOT = REPO_ROOT / "data" / "test-fixtures" / "question-bank"
PILOT_DIR = FIXTURE_ROOT / "pilot"
CURATED_DIR = FIXTURE_ROOT / "curated"

VERIFIER = MathVerifier()


def canonical(rule: str, spec: dict | None = None) -> str:
    value, _details, _evidence = VERIFIER._rules[rule](spec or {})
    return value


SYNTHETIC_RIGHTS_BOUNDARY = {
    "basis": "项目自建合成测试夹具：全部内容由 math-teacher-agent 项目自行创作，仅用于软件测试",
    "included": ["题干", "选项", "答案", "解析", "验证规格"],
    "excluded": [],
    "proof_document_id": "data/test-fixtures/MANIFEST.json",
}
SYNTHETIC_QUALITY_GATE = "合成夹具仅用于验证工作流与门禁逻辑，不构成商业题库内容"
CREATED_AT = "2026-08-16T00:00:00+00:00"

SYNTHETIC_SOURCE = {
    "source_id": "SYN-FIX",
    "document_path": None,
    "source_reference": "项目自建合成测试题",
    "source_page_start": 1,
    "source_page_end": 1,
    "license_status": "question_content_user_declared_usable",
    "allowed_uses": ["display_question", "adapt_question"],
    "excluded_material": [],
    "attribution_required": "confirmed",
    "proof_document_id": "data/test-fixtures/MANIFEST.json",
}

NOT_IMPORTED_SOLUTION = {
    "method": None,
    "steps_latex": [],
    "final_answer": None,
    "author_type": "not_imported",
    "review_status": "to_be_regenerated_and_verified",
}


def base_question(
    question_id: str,
    *,
    chapter: str,
    difficulty: int,
    question_type: str,
    stem_plain: str,
    knowledge_point_ids: list[str],
    options: list[dict],
    answer_value,
    verification_status: str,
    verification_details: list[str],
    document_name: str,
) -> dict:
    single_choice = question_type == "single_choice"
    return {
        "id": question_id,
        "status": "imported",
        "visibility": "private",
        "language": "zh-CN",
        "stem": {"plain_text": stem_plain, "latex": None, "assets": []},
        "question_type": question_type,
        "options": options,
        "answer": {
            "type": "option" if single_choice else "composite",
            "value": answer_value,
            "status": (
                "source_answer_extracted"
                if single_choice
                else "requires_independent_verification"
            ),
            "alternatives": [],
        },
        "solutions": [dict(NOT_IMPORTED_SOLUTION)],
        "curriculum": {
            "curriculum_version": "CN-HS-MATH-2017-2020",
            "textbook": "PEP-A",
            "volume": "必修第一册",
            "chapter": chapter,
            "section": None,
            "knowledge_point_ids": knowledge_point_ids,
            "prerequisite_ids": [],
            "mapping_status": "pilot_candidate",
        },
        "exam": {
            "paper_family": "synthetic-test-fixture",
            "region": None,
            "year": None,
            "original_score": None,
            "competency_tags": [],
        },
        "pedagogy": {
            "difficulty": difficulty,
            "difficulty_confidence": 1.0,
            "estimated_minutes": None,
            "methods": [],
            "common_errors": [],
            "usage_scenarios": ["测试夹具"],
        },
        "verification": {
            "status": verification_status,
            "methods": ["source_boundary_check"],
            "details": verification_details,
        },
        "source": {
            **SYNTHETIC_SOURCE,
            "source_id": f"SYN-FIX-{question_id}",
            "document_name": document_name,
        },
        "provenance": {
            "created_by": "synthetic_fixture_generator",
            "derived_from_question_ids": [],
            "model_run_id": None,
            "duplicate_cluster_id": None,
            "extraction_method": "project_created",
            "topic_heading": None,
        },
        "reviews": [],
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }


SET_CHAPTER = "第一章 集合与常用逻辑用语"
PROBABILITY_CHAPTER = "第七章 随机变量及其分布"
ELLIPSE_CHAPTER = "第三章 圆锥曲线的方程"
FUNCTION_CHAPTER = "第三章 函数的概念与性质"

SET_KP = ["kp_sets_and_logic"]
PROBABILITY_KP = ["kp_probability", "kp_random_variable_distribution"]
ELLIPSE_KP = ["kp_ellipse"]

SET_DOC = "合成测试·集合与常用逻辑用语（项目自建）v1.md"
PROBABILITY_DOC = "合成测试·概率与随机变量（项目自建）v1.md"
ELLIPSE_DOC = "合成测试·圆锥曲线基础（项目自建）v1.md"
FUNCTION_DOC = "合成测试·函数性质（项目自建）v1.md"


def option(key: str, text: str, canonical_value: str | None = None) -> dict:
    item = {"key": key, "plain_text": text, "latex": None}
    if canonical_value is not None:
        item["canonical_value"] = canonical_value
    return item

# --------------------------------------------------------------------------
# Question definitions (project-created simple mathematics)
# --------------------------------------------------------------------------

def set_questions() -> list[dict]:
    specs = [
        {
            "rule": "finite_complement_intersection",
            "spec": {"universe": [1, 2, 3, 4, 5], "set_a": [1, 3, 5], "set_b": [3, 4]},
            "stem": "设全集 U={1,2,3,4,5}，集合 A={1,3,5}，集合 B={3,4}，求 A 与 B 在 U 中的补集的交集。",
            "options": [
                option("A", "{1,5}"), option("B", "{1,3}"),
                option("C", "{2,4}"), option("D", "{3,4}"),
            ],
            "answer": "A",
        },
        {
            "rule": "finite_set_outside_quadratic_interval",
            "spec": {"quadratic": [1, 0, -4], "set_a": [-3, -2, 0, 1, 3]},
            "stem": "已知二次式 x²−4，从有限集 A={−3,−2,0,1,3} 中选出使二次式取正值的所有元素。",
            "options": [
                option("A", "{−3,3}"), option("B", "{−2,0}"),
                option("C", "{1}"), option("D", "{0,1,3}"),
            ],
            "answer": "A",
        },
        {
            "rule": "quadratic_and_exponential_range_complement",
            "spec": {},
            "stem": "设二次不等式 x²−3x+2≥0 的解集为 M，指数函数 y=eˣ 的值域为 N，求 M 与 N 在实数集上的补集的交集。",
            "options": [
                option("A", "(−∞,0]"), option("B", "(0,+∞)"),
                option("C", "(−∞,1]"), option("D", "[0,+∞)"),
            ],
            "answer": "A",
        },
        {
            "rule": "line_cubic_intersection_count",
            "spec": {},
            "stem": "求直线 y=x 与曲线 y=x³ 的公共点的个数。",
            "options": [
                option("A", "3"), option("B", "1"),
                option("C", "2"), option("D", "4"),
            ],
            "answer": "A",
        },
        {
            "rule": "log_domain_proper_subset_count",
            "spec": {"finite_set": [1, 2, 3]},
            "stem": "设有限集 F={1,2,3}，集合 A 由 F 中满足 log₂(2−x) 有意义且其值小于 2 的元素组成，求 A 的真子集个数。",
            "options": [
                option("A", "1"), option("B", "0"),
                option("C", "2"), option("D", "3"),
            ],
            "answer": "A",
        },
        {
            "rule": "union_completion_count",
            "spec": {"fixed_set": [1], "target_set": [1, 2]},
            "stem": "设全集 U={1,2}，集合 A={1}，求满足 A∪X=U 的集合 X 的个数。",
            "options": [
                option("A", "2"), option("B", "1"),
                option("C", "3"), option("D", "4"),
            ],
            "answer": "A",
        },
        {
            "rule": "integer_double_inequality_subset_count",
            "spec": {},
            "stem": "设 M={x∈Z | x²<100<2ˣ}，求集合 M 的子集个数。",
            "options": [
                option("A", "8"), option("B", "4"),
                option("C", "16"), option("D", "6"),
            ],
            "answer": "A",
        },
        {
            "rule": "two_element_nonempty_subset_sum",
            "spec": {"total": 10},
            "stem": "集合 {a,b} 的所有非空子集的元素之和相加等于 10，求 a+b 的值。",
            "options": [
                option("A", "5"), option("B", "10"),
                option("C", "15"), option("D", "20"),
            ],
            "answer": "A",
        },
        {
            "rule": "parameterized_subset_values",
            "spec": {},
            "stem": "已知集合 A={1,m,m²}，集合 B={0,1,4}，若 B⊆A，求 m 的所有可能取值组成的集合。",
            "options": [
                option("A", "{0}"), option("B", "{4}"),
                option("C", "{0,1,4}"), option("D", "{1,4}"),
            ],
            "answer": "A",
            "flawed": True,
        },
        {
            "rule": "integer_threshold_parameter_interval",
            "spec": {},
            "stem": "设 A={0,1,2}，集合 B 为 A 中满足参数条件的子集。若 0 不属于 B 且 1 属于 B，求参数 a 的取值范围。",
            "options": [
                option("A", "(0,3]"), option("B", "[0,3)"),
                option("C", "(0,3)"), option("D", "[0,3]"),
            ],
            "answer": "A",
        },
    ]
    statuses = {
        "q_pilot_set_1_1": "needs_math_review",
        "q_pilot_set_1_2": "needs_formula_review",
        "q_pilot_set_1_3": "needs_formula_review",
        "q_pilot_set_1_4": "needs_formula_review",
        "q_pilot_set_2_1": "needs_math_review",
        "q_pilot_set_2_2": "needs_math_review",
        "q_pilot_set_2_3": "needs_math_review",
        "q_pilot_set_2_4": "needs_math_review",
        "q_pilot_set_3_1": "needs_formula_review",
        "q_pilot_set_3_2": "needs_formula_review",
    }
    questions = []
    for index, item in enumerate(specs, start=1):
        set_index = (index - 1) // 4 + 1
        inner_index = (index - 1) % 4 + 1
        question_id = f"q_pilot_set_{set_index}_{inner_index}"
        questions.append(
            base_question(
                question_id,
                chapter=SET_CHAPTER,
                difficulty=2,
                question_type="single_choice",
                stem_plain=item["stem"],
                knowledge_point_ids=SET_KP,
                options=item["options"],
                answer_value=item["answer"],
                verification_status=statuses[question_id],
                verification_details=[
                    "未导入原解析；解析须独立生成并验算",
                    "合成夹具：来源边界检查占位记录",
                ],
                document_name=SET_DOC,
            )
        )
    return questions

def probability_questions() -> list[dict]:
    definitions = [
        {
            "stem": "甲、乙、丙三名选手按固定轮换进行公平淘汰赛，每局对战的两人获胜概率均为 1/2，先累计输两局者出局。求：(1) 甲连胜前两局并夺冠的概率；(2) 甲最终夺冠的概率；(3) 比赛恰好进行三局结束的概率。",
            "display": "甲连胜夺冠概率为 1/16，甲最终夺冠概率为 3/4，恰好三局结束概率为 7/16",
        },
        {
            "stem": "甲、乙进行发球计分对抗：甲发球时，甲得 1 分的概率为 3/5、乙得 2 分的概率为 2/5；乙发球时规则对称。达到约定终止条件后结束，求甲得分 X 的分布列、期望 E(X)，以及甲某关键组合事件的概率。",
            "display": "P(X=2)=6/25，P(X=3)=77/125，P(X=4)=18/125，E(X)=363/125",
        },
        {
            "stem": "甲队与乙队进行五局三胜对抗，甲队每局获胜概率为 1/3。甲队 3:0 或 3:1 获胜得 3 分，3:2 获胜得 2 分，2:3 落败得 1 分，其余情形得 0 分。求甲队所得积分 X 的分布列、期望 E(X)，以及两队前两局战平的相关组合概率。",
            "display": "P(X=0)=16/27，P(X=1)=16/81，P(X=2)=8/81，P(X=3)=1/9，E(X)=59/81",
        },
        {
            "stem": "慢棋和棋后进入快棋加赛：每局快棋和棋的概率为 1/3，前两局快棋仍和则进入超快棋，超快棋每局和棋概率同样为 1/3。求加赛总局数 X 的分布列与期望 E(X)，以及恰好三局内分出胜负的相关概率。",
            "display": "加赛局数 X 的分布为 P(X=1)=2/3，P(X=2)=2/9，P(X=3)=2/27，P(X=4)=1/27，期望 E(X)=40/27",
        },
        {
            "stem": "七局对抗赛中，甲在前三局发球局获胜概率为 3/5，接发球局获胜概率为 1/2。当甲已胜 2 局或乙已胜 4 局时比赛结束，求剩余比赛局数 X 的分布列、期望 E(X)，以及甲某关键组合事件的概率。",
            "display": "P(X=2)=4/9，P(X=3)=8/27，P(X=4)=13/81，P(X=5)=8/81，E(X)=236/81",
        },
        {
            "stem": "甲、乙、丙三名运动员冲击决赛资格，各人的晋级概率由同一参数 p 表达（1/2<p<3/4，p=2/3 时对应题设数据）。求晋级人数 X 的分布列，并判断三人中晋级概率最高者。",
            "display": "P(X=0)=7/72，P(X=1)=11/32，P(X=2)=29/72，P(X=3)=5/32，晋级概率最高者是甲",
        },
        {
            "stem": "业余队与两名对手进行对抗，参数 p∈(1/3,1/2) 表示某关键胜率。分胜负时总奖金为 4.5 万元，平局时为 3.6 万元。求奖金期望 E(X) 关于 p 的表达式与取值范围，并判断应安排哪位选手首先出场。",
            "display": "E(X)=22/5−3p/10，取值范围为 (17/4,43/10)，应安排乙首先出场",
        },
        {
            "stem": "袋中有新球与旧球，每局开始前摸球决定发球权：摸出新球则甲获得该局优势，每局甲获胜概率为 3/5、乙为 2/5，摸出的球不再放回。求三局两胜制下甲夺冠的概率，以及比赛总局数 X 的分布列与期望 E(X)。",
            "display": "甲夺冠概率为 81/125，P(X=3)=4/15，P(X=4)=97/150，P(X=5)=13/150，E(X)=191/50",
        },
        {
            "stem": "冬季两项比赛中，甲、乙各进行 5 次射击，甲每次命中概率为 4/5，乙为 3/4；每脱靶一次罚时 20 分钟。甲的滑雪用时比乙慢 3 分钟。求两人期望罚时、期望总用时更高者，以及甲某组合事件的概率。",
            "display": "甲期望罚时 4 分钟，乙期望罚时 5 分钟，甲的滑雪劣势为 3 分钟，乙的期望总用时更低",
        },
        {
            "stem": "甲、乙、丙三人进行掷骰问答对抗，甲对乙的胜率为 2/3、对丙的胜率为 1/3，其余对阵胜率均为 1/2，先累计两胜者胜出。求：(1) 甲恰好两局夺冠的概率；(2) 比赛恰好三局结束的概率；(3) 在三局结束的条件下甲胜场数的条件分布与条件期望。",
            "display": "来源答案将联合概率误当作条件概率直接使用",
            "flawed": True,
        },
    ]
    statuses = {"q_pilot_probability_01": "needs_formula_review", "q_pilot_probability_02": "needs_math_review"}
    questions = []
    for index, item in enumerate(definitions, start=1):
        question_id = f"q_pilot_probability_{index:02d}"
        questions.append(
            base_question(
                question_id,
                chapter=PROBABILITY_CHAPTER,
                difficulty=4,
                question_type="composite",
                stem_plain=item["stem"],
                knowledge_point_ids=PROBABILITY_KP,
                options=[],
                answer_value=None,
                verification_status=statuses.get(question_id, "needs_formula_review"),
                verification_details=[
                    "未导入原解析；解析须独立生成并验算",
                    "合成夹具：来源边界检查占位记录",
                ],
                document_name=PROBABILITY_DOC,
            )
        )
    return questions

def ellipse_questions() -> list[dict]:
    definitions = [
        ("已知椭圆 x²/9+y²/4=1，求该椭圆的长轴长。", ["6", "4", "3", "2"], "A", "needs_math_review"),
        ("已知椭圆 x²/25+y²/16=1，求该椭圆的焦距。", ["6", "3", "8", "10"], "A", "needs_math_review"),
        ("已知双曲线 x²/9−y²/16=1，求其实轴长。", ["6", "8", "3", "4"], "A", "needs_math_review"),
        ("已知抛物线 y²=8x，求其焦点到准线的距离。", ["4", "8", "2", "16"], "A", "needs_math_review"),
        ("已知椭圆 x²/16+y²/9=1，求其离心率。", ["3/5", "√7/4", "4/5", "√7/3"], "B", "source_inconsistency_detected"),
        ("已知椭圆 x²/a²+y²/b²=1 (a>b>0) 的焦距为 2c，求其离心率公式。", ["c/a", "a/c", "b/a", "c/b"], "A", "needs_formula_review"),
        ("已知椭圆 x²/16+y²/9=1，求其短轴长。", ["6", "8", "3", "4"], "A", "needs_formula_review"),
        ("已知椭圆 x²/25+y²/9=1 上一点到左焦点的距离为 3，求该点到右焦点的距离。", ["7", "5", "3", "10"], "A", "needs_formula_review"),
        ("已知椭圆的焦点为 (−3,0) 和 (3,0)，且经过点 (4,0)，求椭圆的标准方程。", ["x²/16+y²/7=1", "x²/16+y²/9=1", "x²/25+y²/16=1", "x²/9+y²/7=1"], "A", "needs_formula_review"),
        ("已知椭圆 x²/12+y²/4=1，求其焦点坐标。", ["(±2√2,0)", "(±4,0)", "(0,±2√2)", "(±2,0)"], "A", "needs_math_review"),
    ]
    questions = []
    for index, (stem, option_texts, answer, status) in enumerate(definitions, start=1):
        questions.append(
            base_question(
                f"q_pilot_ellipse_{index:02d}",
                chapter=ELLIPSE_CHAPTER,
                difficulty=3,
                question_type="single_choice",
                stem_plain=stem,
                knowledge_point_ids=ELLIPSE_KP,
                options=[option(key, text) for key, text in zip("ABCD", option_texts)],
                answer_value=answer,
                verification_status=status,
                verification_details=(
                    [
                        "合成夹具样例：来源答案栏与详解结论不一致（模拟 PDF 边界提取问题）",
                        "未导入原解析；解析须独立生成并验算",
                    ]
                    if status == "source_inconsistency_detected"
                    else ["未导入原解析；解析须独立生成并验算", "合成夹具：来源边界检查占位记录"]
                ),
                document_name=ELLIPSE_DOC,
            )
        )
    return questions


def function_questions() -> list[dict]:
    definitions = [
        {
            "stem": "已知定义在 R 上的函数 f(x) 满足 f(3+x)=f(1−x)，且在 (2,+∞) 上严格递减，则下列结论恒成立的是（ ）。",
            "options": [
                option("A", "f(4)<f(1)=f(3)，f(2) 无法确定"),
                option("B", "f(4)<f(2)<f(3)"),
                option("C", "f(1)<f(2)<f(3)"),
                option("D", "f(4)<f(3)<f(2)"),
            ],
            "answer": "B",
            "flawed": True,
            "difficulty": 3,
            "kp": ["kp_function_monotonicity", "kp_function_symmetry"],
        },
        {
            "stem": "已知函数 f(x)=6x−x² 在开区间 (0,6) 上考虑最值，下列说法正确的是（ ）。",
            "options": [
                option("A", "最大值为 9"),
                option("B", "最大值为 8"),
                option("C", "最大值为 9 且最小值为 0"),
                option("D", "不存在最大值"),
            ],
            "answer": "A",
            "difficulty": 2,
            "kp": ["kp_function_extrema", "kp_quadratic_function"],
        },
        {
            "stem": "已知 f(x) 是定义在 R 上的奇函数，且为分段线性函数，解不等式 f(3x)>f(2x−1)。",
            "options": [
                option("A", "(−∞,−1/2)∪(0,1/6)"),
                option("B", "(−∞,−1/2)"),
                option("C", "(0,1/6)"),
                option("D", "(−1/2,1/6)"),
            ],
            "answer": "A",
            "difficulty": 3,
            "kp": ["kp_function_parity", "kp_function_inequality"],
        },
        {
            "stem": "已知函数 f 与 g 的图象关于某条直线对称，且满足给定的函数方程，求 (g∘f)(3) 的值。",
            "options": [
                option("A", "−9/2"), option("B", "−9"),
                option("C", "9/2"), option("D", "9"),
            ],
            "answer": "A",
            "difficulty": 4,
            "kp": ["kp_function_symmetry", "kp_graph_transformation"],
        },
        {
            "stem": "关于函数图象的对称性与周期性，给出四个命题，其中恒成立的命题个数是（ ）。",
            "options": [
                option("A", "3"), option("B", "2"),
                option("C", "4"), option("D", "1"),
            ],
            "answer": "A",
            "difficulty": 4,
            "kp": ["kp_function_symmetry", "kp_function_periodicity"],
        },
    ]
    questions = []
    for index, item in enumerate(definitions, start=1):
        questions.append(
            base_question(
                f"q_function_properties_{index:02d}",
                chapter=FUNCTION_CHAPTER,
                difficulty=item["difficulty"],
                question_type="single_choice",
                stem_plain=item["stem"],
                knowledge_point_ids=item["kp"],
                options=item["options"],
                answer_value=item["answer"],
                verification_status="needs_math_review",
                verification_details=[
                    "未导入原解析；解析须独立生成并验算",
                    "合成夹具：来源边界检查占位记录",
                ],
                document_name=FUNCTION_DOC,
            )
        )
    return questions

# --------------------------------------------------------------------------
# Curation package builders
# --------------------------------------------------------------------------

def curated_solution(method: str, steps: list[str], final_answer: str) -> dict:
    return {
        "method": method,
        "steps_latex": steps,
        "final_answer": final_answer,
        "author_type": "independent_system_draft",
        "review_status": "ready_for_teacher_review",
    }


def candidate(
    question_id: str,
    *,
    stem_plain: str,
    rule: str,
    spec: dict,
    options: list[dict],
    source_answer: str | None,
    expected_canonical_value: str | None,
    computed_answer_display: str | None,
    solution: dict,
    flawed: bool = False,
) -> dict:
    return {
        "question_id": question_id,
        "disposition": (
            "source_inconsistency_detected" if flawed else "verified_candidate"
        ),
        "stem": {"plain_text": stem_plain, "latex": None},
        "options": options,
        "source_answer": source_answer,
        "expected_canonical_value": expected_canonical_value,
        "computed_answer_display": computed_answer_display,
        "solution": solution,
        "verification_spec": {"rule": rule, **spec},
        "source": {
            "source_question_number": question_id,
            "source_page_start": 1,
            "source_page_end": 1,
            "source_reference": "项目自建合成测试题",
            "attribution_required": "confirmed",
        },
    }


def package(package_id: str, source_document: str, candidates: list[dict]) -> dict:
    return {
        "package_id": package_id,
        "schema_version": "1.0-synthetic-fixture",
        "source_document": source_document,
        "source_pages_reviewed": [1],
        "content_policy": SYNTHETIC_QUALITY_GATE,
        "candidates": candidates,
    }


SET_RULES = [
    ("finite_complement_intersection", {"universe": [1, 2, 3, 4, 5], "set_a": [1, 3, 5], "set_b": [3, 4]}),
    ("finite_set_outside_quadratic_interval", {"quadratic": [1, 0, -4], "set_a": [-3, -2, 0, 1, 3]}),
    ("quadratic_and_exponential_range_complement", {}),
    ("line_cubic_intersection_count", {}),
    ("log_domain_proper_subset_count", {"finite_set": [1, 2, 3]}),
    ("union_completion_count", {"fixed_set": [1], "target_set": [1, 2]}),
    ("integer_double_inequality_subset_count", {}),
    ("two_element_nonempty_subset_sum", {"total": 10}),
    ("parameterized_subset_values", {}),
    ("integer_threshold_parameter_interval", {}),
]
SET_STEMS = [
    "设全集 U={1,2,3,4,5}，集合 A={1,3,5}，集合 B={3,4}，求 A 与 B 在 U 中的补集的交集。",
    "已知二次式 x²−4，从有限集 A={−3,−2,0,1,3} 中选出使二次式取正值的所有元素。",
    "设二次不等式 x²−3x+2≥0 的解集为 M，指数函数 y=eˣ 的值域为 N，求 M 与 N 在实数集上的补集的交集。",
    "求直线 y=x 与曲线 y=x³ 的公共点的个数。",
    "设有限集 F={1,2,3}，集合 A 由 F 中满足 log₂(2−x) 有意义且其值小于 2 的元素组成，求 A 的真子集个数。",
    "设全集 U={1,2}，集合 A={1}，求满足 A∪X=U 的集合 X 的个数。",
    "设 M={x∈Z | x²<100<2ˣ}，求集合 M 的子集个数。",
    "集合 {a,b} 的所有非空子集的元素之和相加等于 10，求 a+b 的值。",
    "已知集合 A={1,m,m²}，集合 B={0,1,4}，若 B⊆A，求 m 的所有可能取值组成的集合。",
    "设 A={0,1,2}，集合 B 为 A 中满足参数条件的子集。若 0 不属于 B 且 1 属于 B，求参数 a 的取值范围。",
]
SET_OPTION_TEXTS = [
    ["{1,5}", "{1,3}", "{2,4}", "{3,4}"],
    ["{−3,3}", "{−2,0}", "{1}", "{0,1,3}"],
    ["(−∞,0]", "(0,+∞)", "(−∞,1]", "[0,+∞)"],
    ["3", "1", "2", "4"],
    ["1", "0", "2", "3"],
    ["2", "1", "3", "4"],
    ["8", "4", "16", "6"],
    ["5", "10", "15", "20"],
    ["{0}", "{4}", "{0,1,4}", "{1,4}"],
    ["(0,3]", "[0,3)", "(0,3)", "[0,3]"],
]
SET_SOLUTIONS = [
    ("集合补集与交集运算", ["先求 B 在 U 中的补集", "再计算 A 与补集的交集"], "A"),
    ("有限集代入检验", ["将有限集中每个元素代入二次式", "保留使二次式取正值的元素"], "A"),
    ("区间补集与交集", ["分别确定两个集合", "在数轴上求交集"], "A"),
    ("方程交点个数", ["联立方程并因式分解", "数出不同实根个数"], "A"),
    ("对数定义域与真子集", ["确定对数有意义的元素范围", "按真子集定义计数"], "A"),
    ("并集方程计数", ["枚举全集的所有子集", "筛选满足并集条件的子集"], "A"),
    ("整数筛选与子集计数", ["解两个整数不等式", "按元素个数计算子集数"], "A"),
    ("子集元素和", ["写出两个元素在各非空子集中出现的次数", "解方程求两数之和"], "A"),
    ("集合包含与参数", ["列出参数的所有候选值", "逐一检验包含关系"], "A"),
    ("参数区间", ["由包含条件写出不等式组", "合并得到参数范围"], "A"),
]
PROBABILITY_RULES = [
    "fair_three_player_two_loss_tournament",
    "server_scoring_threshold_game",
    "best_of_five_league_points",
    "chess_tiebreak_game_count",
    "seven_game_match_remaining_length",
    "three_athlete_final_qualification",
    "amateur_team_optimal_prize_range",
    "best_of_three_ball_urn",
    "biathlon_penalty_comparison",
    "three_player_quiz_state_tree",
]
PROBABILITY_STEMS = [
    "甲、乙、丙三名选手按固定轮换进行公平淘汰赛，每局对战的两人获胜概率均为 1/2，先累计输两局者出局。求：(1) 甲连胜前两局并夺冠的概率；(2) 甲最终夺冠的概率；(3) 比赛恰好进行三局结束的概率。",
    "甲、乙进行发球计分对抗：甲发球时，甲得 1 分的概率为 3/5、乙得 2 分的概率为 2/5；乙发球时规则对称。达到约定终止条件后结束，求甲得分 X 的分布列、期望 E(X)，以及甲某关键组合事件的概率。",
    "甲队与乙队进行五局三胜对抗，甲队每局获胜概率为 1/3。甲队 3:0 或 3:1 获胜得 3 分，3:2 获胜得 2 分，2:3 落败得 1 分，其余情形得 0 分。求甲队所得积分 X 的分布列、期望 E(X)，以及两队前两局战平的相关组合概率。",
    "慢棋和棋后进入快棋加赛：每局快棋和棋的概率为 1/3，前两局快棋仍和则进入超快棋，超快棋每局和棋概率同样为 1/3。求加赛总局数 X 的分布列与期望 E(X)，以及恰好三局内分出胜负的相关概率。",
    "七局对抗赛中，甲在前三局发球局获胜概率为 3/5，接发球局获胜概率为 1/2。当甲已胜 2 局或乙已胜 4 局时比赛结束，求剩余比赛局数 X 的分布列、期望 E(X)，以及甲某关键组合事件的概率。",
    "甲、乙、丙三名运动员冲击决赛资格，各人的晋级概率由同一参数 p 表达（1/2<p<3/4，p=2/3 时对应题设数据）。求晋级人数 X 的分布列，并判断三人中晋级概率最高者。",
    "业余队与两名对手进行对抗，参数 p∈(1/3,1/2) 表示某关键胜率。分胜负时总奖金为 4.5 万元，平局时为 3.6 万元。求奖金期望 E(X) 关于 p 的表达式与取值范围，并判断应安排哪位选手首先出场。",
    "袋中有新球与旧球，每局开始前摸球决定发球权：摸出新球则甲获得该局优势，每局甲获胜概率为 3/5、乙为 2/5，摸出的球不再放回。求三局两胜制下甲夺冠的概率，以及比赛总局数 X 的分布列与期望 E(X)。",
    "冬季两项比赛中，甲、乙各进行 5 次射击，甲每次命中概率为 4/5，乙为 3/4；每脱靶一次罚时 20 分钟。甲的滑雪用时比乙慢 3 分钟。求两人期望罚时、期望总用时更高者，以及甲某组合事件的概率。",
    "甲、乙、丙三人进行掷骰问答对抗，甲对乙的胜率为 2/3、对丙的胜率为 1/3，其余对阵胜率均为 1/2，先累计两胜者胜出。求：(1) 甲恰好两局夺冠的概率；(2) 比赛恰好三局结束的概率；(3) 在三局结束的条件下甲胜场数的条件分布与条件期望。",
]
PROBABILITY_DISPLAYS = [
    "甲连胜夺冠概率为 1/16，甲最终夺冠概率为 3/4，恰好三局结束概率为 7/16",
    "P(X=2)=6/25，P(X=3)=77/125，P(X=4)=18/125，E(X)=363/125",
    "P(X=0)=16/27，P(X=1)=16/81，P(X=2)=8/81，P(X=3)=1/9，E(X)=59/81",
    "加赛局数 X 的分布为 P(X=1)=2/3，P(X=2)=2/9，P(X=3)=2/27，P(X=4)=1/27，期望 E(X)=40/27",
    "P(X=2)=4/9，P(X=3)=8/27，P(X=4)=13/81，P(X=5)=8/81，E(X)=236/81",
    "P(X=0)=7/72，P(X=1)=11/32，P(X=2)=29/72，P(X=3)=5/32，晋级概率最高者是甲",
    "E(X)=22/5−3p/10，取值范围为 (17/4,43/10)，应安排乙首先出场",
    "甲夺冠概率为 81/125，P(X=3)=4/15，P(X=4)=97/150，P(X=5)=13/150，E(X)=191/50",
    "甲期望罚时 4 分钟，乙期望罚时 5 分钟，甲的滑雪劣势为 3 分钟，乙的期望总用时更低",
    "来源答案将联合概率误当作条件概率直接使用",
]
PROBABILITY_SOLUTION = curated_solution(
    "枚举状态与期望计算",
    ["按对局规则枚举所有可能状态转移", "合并同类路径得到概率分布", "按定义计算期望与条件概率"],
    "见 computed_answer_display",
)

FUNCTION_RULES = [
    "function_symmetry_monotonic_endpoint",
    "open_interval_quadratic_maximum",
    "odd_piecewise_linear_inequality",
    "graph_symmetry_composition_value",
    "symmetry_antiperiodic_statement_count",
]
FUNCTION_STEMS = [
    "已知定义在 R 上的函数 f(x) 满足 f(3+x)=f(1−x)，且在 (2,+∞) 上严格递减，则下列结论恒成立的是（ ）。",
    "已知函数 f(x)=6x−x² 在开区间 (0,6) 上考虑最值，下列说法正确的是（ ）。",
    "已知 f(x) 是定义在 R 上的奇函数，且为分段线性函数，解不等式 f(3x)>f(2x−1)。",
    "已知函数 f 与 g 的图象关于某条直线对称，且满足给定的函数方程，求 (g∘f)(3) 的值。",
    "关于函数图象的对称性与周期性，给出四个命题，其中恒成立的命题个数是（ ）。",
]
FUNCTION_OPTION_TEXTS = [
    ["f(4)<f(1)=f(3)，f(2) 无法确定", "f(4)<f(2)<f(3)", "f(1)<f(2)<f(3)", "f(4)<f(3)<f(2)"],
    ["最大值为 9", "最大值为 8", "最大值为 9 且最小值为 0", "不存在最大值"],
    ["(−∞,−1/2)∪(0,1/6)", "(−∞,−1/2)", "(0,1/6)", "(−1/2,1/6)"],
    ["−9/2", "−9", "9/2", "9"],
    ["3", "2", "4", "1"],
]
FUNCTION_SOLUTIONS = [
    ("函数对称性与单调性", ["由条件得图象关于直线 x=2 对称", "比较区间上的单调关系"], "A"),
    ("开区间二次函数最值", ["配方确定顶点", "检查顶点是否位于开区间内"], "A"),
    ("奇函数分段线性不等式", ["利用奇偶性化简不等式", "分段讨论得到解集"], "A"),
    ("对称性与复合求值", ["由对称关系求函数值", "代入复合运算"], "A"),
    ("命题判定", ["逐个检验命题的充分性", "统计恒成立命题个数"], "A"),
]

def set_curation_package() -> dict:
    candidates = []
    for index in range(10):
        question_id = f"q_pilot_set_{index // 4 + 1}_{index % 4 + 1}"
        rule, spec = SET_RULES[index]
        computed = canonical(rule, spec)
        flawed = index == 8  # q_pilot_set_3_1
        correct_key = "C" if flawed else "A"
        options = []
        for option_index, text in enumerate(SET_OPTION_TEXTS[index]):
            key = "ABCD"[option_index]
            if flawed:
                value = {"A": "set:0", "B": "set:4", "C": "set:0,1,4", "D": "set:1,4"}[key]
            elif key == correct_key:
                value = computed
            elif index in (0, 1):
                value = f"set:{text}"
            else:
                value = None
            options.append(option(key, text, value))
        method, steps, final_answer = SET_SOLUTIONS[index]
        candidates.append(
            candidate(
                question_id,
                stem_plain=SET_STEMS[index],
                rule=rule,
                spec=spec,
                options=options,
                source_answer="A",
                expected_canonical_value=None,
                computed_answer_display=None,
                solution=curated_solution(method, steps, final_answer),
                flawed=flawed,
            )
        )
    return package("set-10q-synthetic-corrections-v1", SET_DOC, candidates)


def probability_curation_package(kind: str) -> dict:
    if kind == "4q":
        question_indices = [0, 1, 2, 3]
        package_id = "probability-4q-synthetic-corrections-v1"
    else:
        question_indices = [4, 5, 6, 7, 8, 9]
        package_id = "probability-6q-synthetic-corrections-v1"
    candidates = []
    for index in question_indices:
        question_id = f"q_pilot_probability_{index + 1:02d}"
        rule = PROBABILITY_RULES[index]
        computed = canonical(rule)
        flawed = index == 9  # q_pilot_probability_10
        if flawed:
            expected = (
                'composite:{"conditional_distribution":{"0":"1/3","1":"1/3","2":"1/3"},'
                '"conditional_expectation":"1","part1":"1/4",'
                '"probability_game_ends_in_three":"1/2"}'
            )
        else:
            expected = computed
        candidates.append(
            candidate(
                question_id,
                stem_plain=PROBABILITY_STEMS[index],
                rule=rule,
                spec={},
                options=[],
                source_answer=None,
                expected_canonical_value=expected,
                computed_answer_display=PROBABILITY_DISPLAYS[index],
                solution=PROBABILITY_SOLUTION,
                flawed=flawed,
            )
        )
    return package(package_id, PROBABILITY_DOC, candidates)


def function_curation_package() -> dict:
    candidates = []
    for index in range(5):
        question_id = f"q_function_properties_{index + 1:02d}"
        rule = FUNCTION_RULES[index]
        computed = canonical(rule)
        flawed = index == 0
        options = []
        for option_index, text in enumerate(FUNCTION_OPTION_TEXTS[index]):
            key = "ABCD"[option_index]
            if flawed:
                value = (
                    "relation:f(4)<f(1)=f(3);f(2):undetermined"
                    if key == "A"
                    else None
                )
            else:
                value = computed if key == "A" else None
            options.append(option(key, text, value))
        method, steps, final_answer = FUNCTION_SOLUTIONS[index]
        candidates.append(
            candidate(
                question_id,
                stem_plain=FUNCTION_STEMS[index],
                rule=rule,
                spec={},
                options=options,
                source_answer="B" if flawed else "A",
                expected_canonical_value=None,
                computed_answer_display=None,
                solution=curated_solution(method, steps, final_answer),
                flawed=flawed,
            )
        )
    return package("function-properties-5q-synthetic-corrections-v1", FUNCTION_DOC, candidates)


def pilot_batch() -> dict:
    questions = set_questions() + probability_questions() + ellipse_questions()
    return {
        "batch_id": "batch-2026-08-001-pilot-30q",
        "schema_version": "1.0-synthetic-fixture",
        "created_at": CREATED_AT,
        "publication_status": "private_not_publishable",
        "rights_boundary": SYNTHETIC_RIGHTS_BOUNDARY,
        "quality_gate": SYNTHETIC_QUALITY_GATE,
        "question_count": len(questions),
        "questions": questions,
    }


def function_batch() -> dict:
    questions = function_questions()
    return {
        "batch_id": "batch-function-properties-5q-v1",
        "schema_version": "1.0-synthetic-fixture",
        "created_at": CREATED_AT,
        "publication_status": "private_not_publishable",
        "rights_boundary": SYNTHETIC_RIGHTS_BOUNDARY,
        "quality_gate": SYNTHETIC_QUALITY_GATE,
        "question_count": len(questions),
        "questions": questions,
    }

# --------------------------------------------------------------------------
# Self-check: reproduce every hardcoded assertion from the migrated tests
# --------------------------------------------------------------------------

def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def run_self_check(pilot_path: Path, function_pilot_path: Path, curated_paths: dict[str, Path]) -> None:
    from app.modules.question_bank import ReviewCommand

    tmp = Path(tempfile.mkdtemp(prefix="synthetic-fixture-check-"))
    bank = QuestionBank(tmp / "qb.sqlite3", tmp / "media")

    first = bank.import_batch(pilot_path)
    second = bank.import_batch(pilot_path)
    assert first.declared_count == 30 and first.created_count == 30
    assert second.created_count == 0 and second.skipped_count == 30
    assert bank.stats().total == 30
    assert bank.import_batches()[0].batch_id == "batch-2026-08-001-pilot-30q"

    page = bank.search(query="集合", difficulty=2, page_size=50)
    assert page.total == 10
    assert all(item.chapter == SET_CHAPTER for item in page.items)

    curation = bank.apply_curation_package(curated_paths["set"], VERIFIER)
    again = bank.apply_curation_package(curated_paths["set"], VERIFIER)
    assert (curation.applied_count, curation.passed_count, curation.inconsistency_count) == (10, 9, 1)
    assert again.applied_count == 0 and again.skipped_count == 10
    assert bank.get_question("q_pilot_set_1_1").verification_status == "passed"
    flawed = bank.get_question("q_pilot_set_3_1")
    assert flawed.status == "rejected"
    assert flawed.raw["verification"]["computed_canonical_value"] == "set:0,1,4"

    prob4 = bank.apply_curation_package(curated_paths["probability_4q"], VERIFIER)
    prob4_again = bank.apply_curation_package(curated_paths["probability_4q"], VERIFIER)
    assert (prob4.applied_count, prob4.passed_count, prob4.inconsistency_count) == (4, 4, 0)
    assert prob4_again.applied_count == 0 and prob4_again.skipped_count == 4
    tournament = bank.get_question("q_pilot_probability_01")
    assert tournament.verification_status == "passed"
    assert tournament.raw["verification"]["computed_canonical_value"] == (
        'composite:{"part1":"1/16","part2":"3/4","part3":"7/16"}'
    )
    assert bank.get_question("q_pilot_probability_04").raw["verification"][
        "computed_answer"
    ].endswith("E(X)=40/27")

    prob6 = bank.apply_curation_package(curated_paths["probability_6q"], VERIFIER)
    prob6_again = bank.apply_curation_package(curated_paths["probability_6q"], VERIFIER)
    assert (prob6.applied_count, prob6.passed_count, prob6.inconsistency_count) == (6, 5, 1)
    assert prob6_again.applied_count == 0 and prob6_again.skipped_count == 6
    assert bank.get_question("q_pilot_probability_08").verification_status == "passed"
    flawed10 = bank.get_question("q_pilot_probability_10")
    assert flawed10.status == "rejected"
    assert flawed10.verification_status == "source_inconsistency_detected"
    assert flawed10.raw["verification"]["computed_canonical_value"] == (
        'composite:{"conditional_distribution":{"0":"13/59","1":"22/59","2":"24/59"},'
        '"conditional_expectation":"70/59","part1":"5/36",'
        '"probability_game_ends_in_three":"59/144"}'
    )

    imported = bank.import_batch(function_pilot_path)
    fn = bank.apply_curation_package(curated_paths["function"], VERIFIER)
    fn_again = bank.apply_curation_package(curated_paths["function"], VERIFIER)
    assert imported.created_count == 5
    assert (fn.applied_count, fn.passed_count, fn.inconsistency_count) == (5, 4, 1)
    assert fn_again.applied_count == 0 and fn_again.skipped_count == 5
    flawed_fn = bank.get_question("q_function_properties_01")
    assert flawed_fn.status == "rejected"
    assert flawed_fn.verification_status == "source_inconsistency_detected"
    assert flawed_fn.raw["verification"]["computed_canonical_value"] == (
        "relation:f(4)<f(1)=f(3);f(2):undetermined"
    )
    assert bank.get_question("q_function_properties_05").verification_status == "passed"

    stats = bank.stats()
    assert stats.total == 35
    assert stats.by_verification_status["passed"] == 22
    assert stats.by_verification_status["source_inconsistency_detected"] == 4
    assert stats.by_verification_status["needs_math_review"] == 5
    assert stats.by_verification_status["needs_formula_review"] == 4
    assert stats.by_module["sets_logic"] == 10
    assert stats.by_module["analytic_geometry"] == 10
    assert stats.by_module["statistics_probability"] == 10
    assert stats.by_module["functions_derivatives"] == 5
    assert stats.by_work_queue["verified_pending_teacher"] == 22
    assert stats.by_work_queue["source_conflict"] == 4

    bank.review("q_pilot_set_1_1", ReviewCommand(decision="approved", note="合成夹具审核通过"))
    publish = bank.publish("q_pilot_set_1_1")
    assert publish.allowed is True and publish.status == "published"

    service = QuestionVariantService(
        question_bank=bank,
        provider=LocalDiagnosticVariantProvider(),
    )
    result = service.generate(
        "q_pilot_set_1_1",
        QuestionVariantGenerationRequest(
            variant_kind="diagnostic",
            target_difficulty=3,
            instruction="要求学生指出补集范围",
        ),
    )
    variant = result.question
    assert result.mode == "local_rule"
    assert variant.question_id.startswith("q_variant_")
    assert variant.visibility == "private" and variant.review_status == "pending"
    assert variant.verification_status == "passed" and variant.difficulty == 3
    assert "某同学选择了" in variant.stem_plain
    assert variant.raw["provenance"]["derived_from_question_ids"] == ["q_pilot_set_1_1"]
    assert "派生变式" in variant.source_document
    draft = service.save_teacher_draft(
        "q_pilot_set_1_1",
        TeacherVariantDraftCommand(
            question_type="single_choice",
            stem_plain="教师自拟：设全集为实数集，重新判断下列集合关系。",
            answer_value="B",
            final_answer="B",
            solution_steps=["由补集定义判断"],
        ),
    )
    assert draft.raw["generation_request"]["teacher_id"] == "owner_teacher"

    print("self-check OK: import/curation/stats/publish/variant workflows match migrated test contracts")


def main() -> None:
    pilot_path = PILOT_DIR / "batch-synthetic-set-probability-30q-v1.json"
    function_pilot_path = PILOT_DIR / "function-properties-synthetic-5q-v1.json"
    curated_paths = {
        "set": CURATED_DIR / "set-10q-synthetic-corrections-v1.json",
        "probability_4q": CURATED_DIR / "probability-4q-synthetic-corrections-v1.json",
        "probability_6q": CURATED_DIR / "probability-6q-synthetic-corrections-v1.json",
        "function": CURATED_DIR / "function-properties-5q-synthetic-corrections-v1.json",
    }
    write_json(pilot_path, pilot_batch())
    write_json(function_pilot_path, function_batch())
    write_json(curated_paths["set"], set_curation_package())
    write_json(curated_paths["probability_4q"], probability_curation_package("4q"))
    write_json(curated_paths["probability_6q"], probability_curation_package("6q"))
    write_json(curated_paths["function"], function_curation_package())
    run_self_check(pilot_path, function_pilot_path, curated_paths)
    print("fixtures written to", FIXTURE_ROOT)


if __name__ == "__main__":
    main()
