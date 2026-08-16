"""SearchPlanBuilder：把 SearchIntent 变成可执行、可解释、可展示的结构化计划。

只保存可安全展示的结构化检索决策（applied_filters / soft_preferences /
relaxations / counts），绝不含模型私有思维过程。
"""

from __future__ import annotations

import uuid

from .domain import SearchIntent, SearchPlan, SearchPlanStep


def build_search_plan(intent: SearchIntent) -> SearchPlan:
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    applied_filters: dict[str, object] = {}
    for constraint in intent.hard_constraints():
        applied_filters[constraint.field] = constraint.value
    soft_preferences = [
        f"{constraint.field}={constraint.value}" for constraint in intent.soft_constraints()
    ]

    steps = [
        SearchPlanStep(step=1, title="resolve_curriculum", detail={
            "knowledge_point_ids": intent.curriculum.knowledge_point_ids,
            "chapter": intent.curriculum.chapter,
            "volume": intent.curriculum.volume,
        }),
        SearchPlanStep(step=2, title="apply_hard_filters", detail=dict(applied_filters)),
        SearchPlanStep(step=3, title="search_candidates", detail={
            "count": intent.count,
            "limit_applied": intent.limit_applied,
        }),
        SearchPlanStep(step=4, title="apply_rights_publication_visibility_gate", detail={}),
        SearchPlanStep(step=5, title="verification_enrichment", detail={
            "require_verified": intent.require_verified,
        }),
        SearchPlanStep(step=6, title="deduplicate", detail={"enabled": intent.deduplicate}),
        SearchPlanStep(step=7, title="similarity_diversity", detail={"enabled": intent.diversify}),
        SearchPlanStep(step=8, title="difficulty_knowledge_rerank", detail={}),
        SearchPlanStep(step=9, title="select_top_n", detail={"requested_count": intent.count}),
        SearchPlanStep(step=10, title="generate_explanation", detail={}),
    ]
    return SearchPlan(
        plan_id=plan_id,
        intent_summary={
            "grade": intent.grade,
            "knowledge_points": intent.knowledge_points,
            "sub_knowledge_points": intent.sub_knowledge_points,
            "difficulty": intent.difficulty or intent.difficulty_range,
            "question_types": intent.question_types,
            "count": intent.count,
            "teaching_usage": intent.teaching_usage,
        },
        steps=steps,
        applied_filters=applied_filters,
        soft_preferences=soft_preferences,
    )
