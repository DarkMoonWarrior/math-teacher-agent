"""生成 Search Agent 测试用合成题库 fixture（项目自建，不含任何第三方内容）。

用途：验证 SearchAgentPipeline 的 grounding / hard-soft 过滤 / 去重 / 多样性
逻辑。全部题目由 math-teacher-agent 项目自行创作，仅用于软件测试，
不属于商业题库内容。
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "test-fixtures"
    / "search-agent"
    / "search-agent-synthetic-14q-v1.json"
)

CREATED_AT = "2026-08-16T09:00:00+08:00"


def _question(
    question_id: str,
    stem: str,
    *,
    question_type: str,
    difficulty: int,
    chapter: str,
    volume: str,
    knowledge_point_ids: list[str],
    year: int | None,
    region: str | None,
    options: dict[str, str] | None = None,
    answer: str | None = None,
) -> dict:
    return {
        "id": question_id,
        "status": "imported",
        "visibility": "private",
        "language": "zh-CN",
        "stem": {"plain_text": stem, "latex": None, "assets": []},
        "question_type": question_type,
        "options": [{"key": key, "plain_text": text, "latex": None} for key, text in (options or {}).items()],
        "answer": {
            "type": "option" if options else "text",
            "value": answer,
            "status": "source_answer_extracted",
            "alternatives": [],
        },
        "solutions": [
            {
                "method": None,
                "steps_latex": [],
                "final_answer": None,
                "author_type": "project_created",
                "review_status": "approved",
            }
        ],
        "curriculum": {
            "curriculum_version": "CN-HS-MATH-2017-2020",
            "textbook": "PEP-A",
            "volume": volume,
            "chapter": chapter,
            "section": None,
            "knowledge_point_ids": knowledge_point_ids,
            "prerequisite_ids": [],
            "mapping_status": "synthetic_fixture",
        },
        "exam": {
            "paper_family": "synthetic-search-agent-fixture",
            "region": region,
            "year": year,
            "original_score": None,
            "competency_tags": [],
        },
        "pedagogy": {
            "difficulty": difficulty,
            "difficulty_confidence": 1.0,
            "estimated_minutes": None,
            "methods": [],
            "common_errors": [],
            "usage_scenarios": ["Search Agent 合成测试"],
        },
        "verification": {
            "status": "passed",
            "methods": ["source_boundary_check"],
            "details": ["项目自建合成夹具：仅用于软件测试，不构成商业题库内容"],
        },
        "source": {
            "source_id": f"SYN-FIX-{question_id}",
            "document_path": None,
            "source_reference": "项目自建合成测试题",
            "source_page_start": 1,
            "source_page_end": 1,
            "license_status": "question_content_user_declared_usable",
            "allowed_uses": ["display_question", "adapt_question"],
            "excluded_material": [],
            "attribution_required": "confirmed",
            "proof_document_id": "data/test-fixtures/MANIFEST.json",
            "document_name": "合成测试·Search Agent 检索验证（项目自建）v1.md",
        },
        "provenance": {
            "created_by": "generate_search_agent_fixtures.py",
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


QUESTIONS = [
    # -- 椭圆焦点弦（难/中档，年份/地区可过滤） --------------------------
    _question(
        "q_sa_focus_01",
        "已知椭圆 x²/25+y²/16=1，过右焦点 F 且斜率为 1 的直线与椭圆交于 A、B 两点，求焦点弦 AB 的长度。",
        question_type="single_choice", difficulty=3,
        chapter="圆锥曲线的方程", volume="选择性必修第一册",
        knowledge_point_ids=["kp_s1_3_1_01", "kp_s1_3_3_05"],
        year=2025, region="江苏",
        options={"A": "32/5", "B": "16/5", "C": "25/8", "D": "8/5"}, answer="A",
    ),
    _question(
        "q_sa_focus_02",
        "已知椭圆 x²/16+y²/9=1，过右焦点的直线 l 交椭圆于 A、B 两点，当焦点弦 AB 的中点横坐标为 1 时，求直线 l 的斜率。",
        question_type="single_choice", difficulty=4,
        chapter="圆锥曲线的方程", volume="选择性必修第一册",
        knowledge_point_ids=["kp_s1_3_1_01", "kp_s1_3_3_05"],
        year=2025, region="江苏",
        options={"A": "±3/4", "B": "±4/3", "C": "±1/2", "D": "±2"}, answer="B",
    ),
    _question(
        "q_sa_focus_03",
        "椭圆 x²/9+y²/5=1 的过焦点且垂直于长轴的焦点弦长度为（ ）。",
        question_type="fill_blank", difficulty=3,
        chapter="圆锥曲线的方程", volume="选择性必修第一册",
        knowledge_point_ids=["kp_s1_3_1_01", "kp_s1_3_3_05"],
        year=2025, region="江苏", answer="10/3",
    ),
    _question(
        "q_sa_focus_04",
        "设椭圆 x²/20+y²/4=1 的左焦点为 F，过 F 作倾斜角为 45° 的焦点弦 AB，求线段 AB 的长。",
        question_type="solution", difficulty=4,
        chapter="圆锥曲线的方程", volume="选择性必修第一册",
        knowledge_point_ids=["kp_s1_3_1_01", "kp_s1_3_3_05"],
        year=2025, region="江苏", answer="16√2/9",
    ),
    _question(
        "q_sa_focus_05",
        "已知椭圆 x²/13+y²/4=1，过右焦点且斜率为 2 的焦点弦所在直线的方程为（ ）。",
        question_type="single_choice", difficulty=3,
        chapter="圆锥曲线的方程", volume="选择性必修第一册",
        knowledge_point_ids=["kp_s1_3_1_01", "kp_s1_3_3_05"],
        year=2024, region="江苏",
        options={"A": "y=2x-6", "B": "y=2x+6", "C": "y=2x-4", "D": "y=2x+4"}, answer="A",
    ),
    _question(
        "q_sa_focus_06",
        "椭圆 x²/12+y²/3=1 中，过左焦点作倾斜角为 30° 的焦点弦，求该焦点弦的长度。",
        question_type="single_choice", difficulty=3,
        chapter="圆锥曲线的方程", volume="选择性必修第一册",
        knowledge_point_ids=["kp_s1_3_1_01", "kp_s1_3_3_05"],
        year=2024, region="山东",
        options={"A": "2", "B": "4", "C": "6", "D": "8"}, answer="B",
    ),
    # -- 椭圆基础（基础题，无年份/地区） --------------------------------
    _question(
        "q_sa_ellipse_01",
        "椭圆 x²/9+y²/5=1 的长轴长为（ ）。",
        question_type="single_choice", difficulty=1,
        chapter="圆锥曲线的方程", volume="选择性必修第一册",
        knowledge_point_ids=["kp_s1_3_1_01"],
        year=None, region=None,
        options={"A": "3", "B": "6", "C": "5", "D": "10"}, answer="B",
    ),
    _question(
        "q_sa_ellipse_02",
        "椭圆 x²/4+y²=1 的焦距为（ ）。",
        question_type="fill_blank", difficulty=1,
        chapter="圆锥曲线的方程", volume="选择性必修第一册",
        knowledge_point_ids=["kp_s1_3_1_01"],
        year=None, region=None, answer="2√3",
    ),
    # -- 椭圆相近模型（不含焦点弦，作为 soft relaxation 的候选） --------
    _question(
        "q_sa_ellipse_03",
        "已知椭圆 x²/16+y²/9=1，其离心率为（ ）。",
        question_type="single_choice", difficulty=2,
        chapter="圆锥曲线的方程", volume="选择性必修第一册",
        knowledge_point_ids=["kp_s1_3_1_01", "kp_s1_3_3_05"],
        year=None, region=None,
        options={"A": "√7/4", "B": "3/4", "C": "4/5", "D": "√7/3"}, answer="A",
    ),
    _question(
        "q_sa_ellipse_04",
        "椭圆 x²/10+y²/6=1 的焦点坐标为（ ）。",
        question_type="fill_blank", difficulty=2,
        chapter="圆锥曲线的方程", volume="选择性必修第一册",
        knowledge_point_ids=["kp_s1_3_1_01", "kp_s1_3_3_05"],
        year=None, region=None, answer="(±2,0)",
    ),
    # -- 导数（压轴档） --------------------------------------------------
    _question(
        "q_sa_deriv_01",
        "已知函数 f(x)=x³-3x+1，求函数 f(x) 的单调递增区间。",
        question_type="solution", difficulty=5,
        chapter="一元函数的导数及其应用", volume="选择性必修第二册",
        knowledge_point_ids=["kp_s2_5_1_03", "kp_s2_5_3_01"],
        year=None, region=None, answer="(-∞,-1)∪(1,+∞)",
    ),
    _question(
        "q_sa_deriv_02",
        "已知 f(x) 在 R 上可导且 f'(x)>f(x)，构造函数 g(x)=f(x)/eˣ，证明 g(x) 单调递增。",
        question_type="solution", difficulty=5,
        chapter="一元函数的导数及其应用", volume="选择性必修第二册",
        knowledge_point_ids=["kp_s2_5_1_03", "kp_s2_5_3_01"],
        year=None, region=None, answer="略（构造函数法）",
    ),
    # -- 集合（基础，跨章节） --------------------------------------------
    _question(
        "q_sa_set_01",
        "已知集合 A={1,2,3}，B={2,3,4}，则 A∩B=（ ）。",
        question_type="single_choice", difficulty=1,
        chapter="集合与常用逻辑用语", volume="必修第一册",
        knowledge_point_ids=["kp_r1_1_1_01"],
        year=None, region=None,
        options={"A": "{2,3}", "B": "{1,4}", "C": "{1,2,3,4}", "D": "∅"}, answer="A",
    ),
    _question(
        "q_sa_set_02",
        "已知集合 A={x|x>1}，B={x|x<3}，则 A∩B 用区间表示为（ ）。",
        question_type="fill_blank", difficulty=1,
        chapter="集合与常用逻辑用语", volume="必修第一册",
        knowledge_point_ids=["kp_r1_1_1_01"],
        year=None, region=None, answer="(1,3)",
    ),
]


def main() -> None:
    payload = {
        "batch_id": "search-agent-synthetic-14q",
        "schema_version": "1.0-synthetic-fixture",
        "created_at": CREATED_AT,
        "publication_status": "private_not_publishable",
        "rights_boundary": {
            "basis": "项目自建合成测试夹具：全部内容由 math-teacher-agent 项目自行创作，仅用于软件测试",
            "included": ["题干", "选项", "答案", "解析", "验证规格"],
            "excluded": [],
            "proof_document_id": "data/test-fixtures/MANIFEST.json",
        },
        "quality_gate": "合成夹具仅用于验证 Search Agent 工作流与门禁逻辑，不构成商业题库内容",
        "question_count": len(QUESTIONS),
        "questions": QUESTIONS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()