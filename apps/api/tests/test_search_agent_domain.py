"""SearchIntent 解析与 SearchPlan 构建测试（确定性、可离线回归）。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.core.config import get_settings
from app.modules.curriculum.catalog import CsvCurriculumCatalog
from app.modules.search_agent import SearchIntentParser, build_search_plan


def _parser(*, reference_date: date | None = None) -> SearchIntentParser:
    csv_path = get_settings().curriculum_csv.resolve()
    catalog = CsvCurriculumCatalog(Path(csv_path))
    return SearchIntentParser(catalog, reference_date=reference_date)


def test_default_count_and_usage():
    intent = _parser().parse("给我几道椭圆题")
    assert intent.count == 5
    assert intent.requested_count is None
    assert intent.teaching_usage == "general"
    assert intent.diversify is True
    assert intent.deduplicate is True


def test_count_parsed_and_hard_cap_applied():
    intent = _parser().parse("找 8 道导数题")
    assert intent.count == 8
    assert intent.limit_applied is False
    capped = _parser().parse("给我 100 道题")
    assert capped.count == 20
    assert capped.limit_applied is True
    assert any("上限" in warning for warning in capped.parse_warnings)


def test_hard_vs_soft_markers():
    intent = _parser().parse("只要2025江苏的圆锥曲线选择题，4道，最好是焦点弦")
    year = next(c for c in intent.constraints if c.field == "year")
    region = next(c for c in intent.constraints if c.field == "regions")
    types = next(c for c in intent.constraints if c.field == "question_types")
    assert (year.strength, region.strength, types.strength) == ("hard", "hard", "hard")
    assert intent.regions == ["江苏"]
    assert intent.year_from == 2025 and intent.year_to == 2025
    assert intent.question_types == ["single_choice"]
    assert intent.count == 4


def test_relative_year_window_uses_injected_beijing_calendar_year():
    intent = _parser(reference_date=date(2026, 1, 1)).parse("只要近两年江苏的导数题")
    assert intent.year_from == 2025
    assert intent.year_to == 2026
    year = next(c for c in intent.constraints if c.field == "year")
    assert year.value == [2025, 2026]
    assert year.strength == "hard"
    assert any("北京时间自然年" in warning and "2025—2026" in warning for warning in intent.parse_warnings)


def test_relative_year_window_supports_arabic_and_chinese_numbers():
    parser = _parser(reference_date=date(2026, 8, 21))
    arabic = parser.parse("近3年的椭圆题")
    chinese = parser.parse("近十二年的椭圆题")
    assert (arabic.year_from, arabic.year_to) == (2024, 2026)
    assert (chinese.year_from, chinese.year_to) == (2015, 2026)


def test_vague_recent_year_never_becomes_an_invented_hard_filter():
    intent = _parser(reference_date=date(2026, 8, 21)).parse("找近年江苏地区的导数解答题")
    assert intent.year_from is None
    assert intent.year_to is None
    assert not any(c.field == "year" for c in intent.constraints)
    assert any("未设置年份硬条件" in warning and "近两年" in warning for warning in intent.parse_warnings)


def test_explicit_year_range_takes_precedence_over_relative_wording():
    intent = _parser(reference_date=date(2035, 1, 1)).parse("优先找2023到2025年的题，不要近年的")
    assert (intent.year_from, intent.year_to) == (2023, 2025)
    assert not any("未设置年份硬条件" in warning for warning in intent.parse_warnings)


def test_soft_preference_recorded_as_soft():
    intent = _parser().parse("找8道导数压轴题，最好覆盖构造函数")
    soft = [c for c in intent.constraints if c.strength == "soft"]
    assert any(c.field == "knowledge_points" and "构造函数" in str(c.value) for c in soft)
    assert "构造函数" in intent.sub_knowledge_points
    assert intent.difficulty == 5


def test_difficulty_range():
    intent = _parser().parse("中等偏难的椭圆题")
    assert intent.difficulty is None
    assert intent.difficulty_range == [3, 4]


def test_slightly_hard_maps_to_difficulty_four():
    intent = _parser().parse("找几道稍难一点的导数题")
    assert intent.difficulty == 4
    assert intent.difficulty_range == []


def test_teaching_usage_is_soft_and_mapped():
    intent = _parser().parse("适合课堂例题的椭圆题")
    assert intent.teaching_usage == "classroom_example"
    usage = next(c for c in intent.constraints if c.field == "teaching_usage")
    assert usage.strength == "soft"
    homework = _parser().parse("给学生课后练习的函数题")
    assert homework.teaching_usage == "homework"
    assert _parser().parse("找三道例题").teaching_usage == "classroom_example"
    assert _parser().parse("找一组函数复习题").teaching_usage == "exam_review"


def test_negative_question_type_is_not_reversed_into_positive_constraint():
    intent = _parser().parse("找 5 道函数题，不要填空题")
    assert intent.question_types == []
    assert not any(c.field == "question_types" for c in intent.constraints)
    assert any("排除题型" in warning for warning in intent.parse_warnings)

    mixed = _parser().parse("不要填空题，只要选择题")
    assert mixed.question_types == ["single_choice"]


def test_exclude_ids_and_similar():
    intent = _parser().parse("不要和 Q123 太像的题")
    assert intent.exclude_similar_to == ["Q123"]
    assert intent.exclude_question_ids == ["Q123"]


def test_require_verified():
    intent = _parser().parse("只要验证过的椭圆题")
    assert intent.require_verified is True
    verified = next(c for c in intent.constraints if c.field == "require_verified")
    assert verified.strength == "hard"


def test_allow_related_fallback_markers():
    intent = _parser().parse("给我5道椭圆题，最好焦点弦，没有的话相近模型也可以")
    assert intent.allow_related_fallback is True
    assert "焦点弦" in intent.sub_knowledge_points


def test_curriculum_mapping_grounded_in_catalog():
    intent = _parser().parse("给我找5道高二椭圆焦点弦，中等偏难")
    assert intent.grade == "高二"
    assert "焦点弦" in intent.sub_knowledge_points
    assert intent.curriculum.knowledge_point_ids
    assert all(node.startswith("kp_") for node in intent.curriculum.knowledge_point_ids)
    assert intent.curriculum.volume == "选择性必修第一册"
    assert intent.curriculum.chapter is not None


def test_unmapped_terms_never_become_fake_node_ids():
    intent = _parser().parse("构造函数的导数题")
    # 构造函数不是 catalog 节点：绝不能出现臆造的 node id。
    assert all(
        node_id.startswith("kp_") or node_id.startswith("pep_a")
        for node_id in intent.curriculum.knowledge_point_ids
    )
    assert "构造函数" in intent.sub_knowledge_points


def test_volume_parsed_without_hallucination():
    intent = _parser().parse("必修一的集合题")
    assert intent.volume == "必修第一册"
    # 年级不是册次的必然映射：未给出年级时不得臆造年级。
    assert intent.grade is None


def test_plan_contains_ten_structured_steps():
    intent = _parser().parse("只要2025江苏的圆锥曲线选择题，4道")
    plan = build_search_plan(intent)
    assert [step.title for step in plan.steps] == [
        "resolve_curriculum",
        "apply_hard_filters",
        "search_candidates",
        "apply_rights_publication_visibility_gate",
        "verification_enrichment",
        "deduplicate",
        "similarity_diversity",
        "difficulty_knowledge_rerank",
        "select_top_n",
        "generate_explanation",
    ]
    assert plan.applied_filters.get("year") == [2025, 2025]
    assert plan.applied_filters.get("regions") == ["江苏"]
    # 教学用途是 soft 偏好，不进入 hard filters。
    assert "teaching_usage" not in plan.applied_filters
    assert plan.soft_preferences == []
    soft_plan = build_search_plan(_parser().parse("椭圆题，适合课堂例题"))
    assert any("teaching_usage" in item for item in soft_plan.soft_preferences)


def test_constraints_carry_origin_and_confidence():
    intent = _parser().parse("只要2025江苏的圆锥曲线选择题")
    for constraint in intent.constraints:
        assert constraint.strength in ("hard", "soft", "default")
        assert constraint.origin in ("explicit", "inferred", "system_default")
        assert 0.0 <= constraint.confidence <= 1.0
