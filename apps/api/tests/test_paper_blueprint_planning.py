from fastapi.testclient import TestClient

from app.main import app
from app.modules.exam_papers import (
    PaperBlueprintBrief,
    PaperBlueprintPlanning,
    PaperBlueprintPlanningError,
)


def test_plans_explicit_high_school_midterm_without_side_effects() -> None:
    blueprint = PaperBlueprintPlanning().plan(
        PaperBlueprintBrief(
            brief="组一份高二期中卷，120 分钟，总分 150 分，覆盖函数、导数与圆锥曲线，中等偏难"
        )
    )

    assert blueprint.status == "draft"
    assert blueprint.editable is True
    assert blueprint.confirmed is False
    assert blueprint.saved is False
    assert blueprint.grade_scope == "高二"
    assert blueprint.duration_minutes == 120
    assert blueprint.target_score == 150
    assert blueprint.difficulty_profile == "challenge"
    assert blueprint.knowledge_points == ["函数", "导数", "圆锥曲线"]
    assert sum(section.target_score for section in blueprint.sections) == 150
    assert blueprint.side_effects == []
    assert blueprint.trust_policy.auto_authoring_allowed is False
    assert blueprint.trust_policy.private_question_policy == "explicit_owner_selection_only"


def test_plans_visible_defaults_and_explicit_open_response_count() -> None:
    blueprint = PaperBlueprintPlanning().plan(
        PaperBlueprintBrief(brief="组一份导数专题测验，中等难度，含 3 道解答题")
    )

    assert blueprint.teaching_usage == "专题测验"
    assert blueprint.duration_minutes == 60
    assert blueprint.target_score == 100
    assert blueprint.difficulty_profile == "balanced"
    assert next(
        section.question_count
        for section in blueprint.sections
        if section.question_type == "open_response"
    ) == 3
    assert any("年级" in assumption for assumption in blueprint.assumptions)
    assert any("考试时间" in assumption for assumption in blueprint.assumptions)
    assert any("总分" in assumption for assumption in blueprint.assumptions)


def test_rejects_explicit_university_scope() -> None:
    try:
        PaperBlueprintPlanning().plan(
            PaperBlueprintBrief(brief="组一份大学数学分析与傅里叶分析综合试卷")
        )
    except PaperBlueprintPlanningError as exc:
        assert "只支持中国普通高中数学" in str(exc)
    else:
        raise AssertionError("explicit university scope must be rejected")


def test_http_plans_blueprint_without_owner_or_trust_inputs() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/exam-papers/blueprints/plan",
        json={"brief": "组一份函数性质随堂练习，20 分钟，以基础巩固为主"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["duration_minutes"] == 20
    assert payload["target_score"] == 40
    assert payload["difficulty_profile"] == "foundation"
    assert payload["side_effects"] == []

    forged = client.post(
        "/api/v1/exam-papers/blueprints/plan",
        json={
            "brief": "组一份函数性质随堂练习",
            "owner_id": "another_teacher",
            "verification_policy": "bypass",
        },
    )
    assert forged.status_code == 422


def test_http_returns_controlled_error_for_university_scope() -> None:
    response = TestClient(app).post(
        "/api/v1/exam-papers/blueprints/plan",
        json={"brief": "组一份本科线性代数期末卷"},
    )

    assert response.status_code == 422
    assert "只支持中国普通高中数学" in response.json()["detail"]
