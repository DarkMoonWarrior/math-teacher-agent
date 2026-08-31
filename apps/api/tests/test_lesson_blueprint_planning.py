from fastapi.testclient import TestClient

from app.main import app
from app.modules.curriculum import CurriculumNode, InMemoryCurriculumCatalog
from app.modules.lesson_plans import (
    LessonBlueprintBrief,
    LessonBlueprintPlanning,
    LessonBlueprintPlanningError,
)
from app.modules.teacher_memory import (
    TeacherPlanningDefaults,
    TeacherPlanningPreference,
    TeacherPreferenceSource,
)


def _catalog() -> InMemoryCurriculumCatalog:
    common = {
        "description": "",
        "prerequisite_node_ids": [],
        "primary_competencies": [],
        "typical_question_types": [],
        "common_errors": [],
        "gaokao_priority": "high",
        "status": "ready_for_teacher_review",
        "reviewed_by": "teacher",
    }
    return InMemoryCurriculumCatalog(
        [
            CurriculumNode(
                node_id="root",
                parent_id=None,
                volume="必修第一册",
                node_type="volume",
                code="R1",
                name="必修第一册",
                **common,
            ),
            CurriculumNode(
                node_id="chapter",
                parent_id="root",
                volume="必修第一册",
                node_type="chapter",
                code="3",
                name="第三章 函数的概念与性质",
                **common,
            ),
            CurriculumNode(
                node_id="section",
                parent_id="chapter",
                volume="必修第一册",
                node_type="section",
                code="3.2",
                name="函数的基本性质",
                description="单调性、最值与奇偶性",
                prerequisite_node_ids=[],
                primary_competencies=["逻辑推理", "直观想象"],
                typical_question_types=["选择题"],
                common_errors=["忽略定义域和区间"],
                gaokao_priority="high",
                status="ready_for_teacher_review",
                reviewed_by="teacher",
            ),
            CurriculumNode(
                node_id="kp-monotonicity",
                parent_id="section",
                volume="必修第一册",
                node_type="knowledge_point",
                code="3.2.1",
                name="函数单调性",
                description="增减函数的定义和图象判断",
                prerequisite_node_ids=[],
                primary_competencies=["逻辑推理"],
                typical_question_types=["单调性判断"],
                common_errors=["任取两点步骤不完整"],
                gaokao_priority="high",
                status="ready_for_teacher_review",
                reviewed_by="teacher",
            ),
        ]
    )


def test_plans_grounded_editable_lesson_without_side_effects() -> None:
    blueprint = LessonBlueprintPlanning(curriculum_catalog=_catalog()).plan(
        LessonBlueprintBrief(
            brief="为高一函数单调性准备一份 45 分钟新授课教案，学生基础中等，安排 4 道练习"
        )
    )

    assert blueprint.status == "lesson_blueprint_draft"
    assert blueprint.editable is True
    assert blueprint.confirmed is False
    assert blueprint.saved is False
    assert blueprint.grade_scope == "高一"
    assert blueprint.lesson_type == "new_lesson"
    assert blueprint.duration_minutes == 45
    assert blueprint.question_count == 4
    assert blueprint.selected_curriculum_node_id == "kp-monotonicity"
    assert blueprint.curriculum_candidates[0].catalog_status == "ready_for_teacher_review"
    assert sum(item.minutes for item in blueprint.phases) == 45
    assert blueprint.side_effects == []
    assert blueprint.trust_policy.auto_save_allowed is False
    assert blueprint.trust_policy.question_policy == "not_selected_during_planning"


def test_plans_visible_defaults_for_underspecified_review_lesson() -> None:
    blueprint = LessonBlueprintPlanning(curriculum_catalog=_catalog()).plan(
        LessonBlueprintBrief(brief="设计一节函数单调性专题复习课")
    )

    assert blueprint.lesson_type == "review"
    assert blueprint.lesson_format == "专题复习课"
    assert blueprint.duration_minutes == 45
    assert blueprint.question_count == 3
    assert any("年级" in item for item in blueprint.assumptions)
    assert any("课时" in item for item in blueprint.assumptions)
    assert any("学情" in item for item in blueprint.assumptions)
    assert any("例题与练习数量" in item for item in blueprint.assumptions)


def test_teacher_defaults_are_visible_and_explicit_brief_still_wins() -> None:
    defaults = TeacherPlanningDefaults(preferences=[
        TeacherPlanningPreference(
            key="default_grade",
            label="默认年级",
            value="高三",
            source=TeacherPreferenceSource(),
        ),
        TeacherPlanningPreference(
            key="default_lesson_minutes",
            label="默认课时",
            value=50,
            source=TeacherPreferenceSource(),
        ),
    ])
    planning = LessonBlueprintPlanning(curriculum_catalog=_catalog())

    defaulted = planning.plan(
        LessonBlueprintBrief(brief="设计一节函数单调性专题复习课"),
        defaults=defaults,
    )
    assert defaulted.grade_scope == "高三"
    assert defaulted.duration_minutes == 50
    assert [item.key for item in defaulted.applied_preferences] == [
        "default_grade",
        "default_lesson_minutes",
    ]
    assert all(item.source.confidence == 1 for item in defaulted.applied_preferences)
    assert any("本次可直接修改覆盖" in item for item in defaulted.assumptions)

    explicit = planning.plan(
        LessonBlueprintBrief(brief="为高一函数单调性准备一节 30 分钟专题复习课"),
        defaults=defaults,
    )
    assert explicit.grade_scope == "高一"
    assert explicit.duration_minutes == 30
    assert explicit.applied_preferences == []


def test_rejects_explicit_university_scope() -> None:
    try:
        LessonBlueprintPlanning(curriculum_catalog=_catalog()).plan(
            LessonBlueprintBrief(brief="设计一节本科数学分析与傅里叶分析课程")
        )
    except LessonBlueprintPlanningError as exc:
        assert "只支持中国普通高中数学" in str(exc)
    else:
        raise AssertionError("explicit university scope must be rejected")


def test_http_plans_lesson_blueprint_without_owner_or_trust_inputs() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/lesson-plans/blueprints/plan",
        json={"brief": "为高二椭圆第一课时准备一份 45 分钟新授课教案"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["grade_scope"] == "高二"
    assert payload["duration_minutes"] == 45
    assert payload["curriculum_query"] == "椭圆"
    assert payload["selected_curriculum_node_id"]
    assert payload["side_effects"] == []

    forged = client.post(
        "/api/v1/lesson-plans/blueprints/plan",
        json={
            "brief": "为高二椭圆准备一份教案",
            "owner_id": "another_teacher",
            "auto_save_allowed": True,
        },
    )
    assert forged.status_code == 422


def test_http_returns_controlled_error_for_university_scope() -> None:
    response = TestClient(app).post(
        "/api/v1/lesson-plans/blueprints/plan",
        json={"brief": "为大学线性代数设计一节矩阵课程"},
    )

    assert response.status_code == 422
    assert "只支持中国普通高中数学" in response.json()["detail"]
