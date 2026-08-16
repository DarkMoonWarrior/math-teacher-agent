"""确定性检索排序 / 去重 / 多样性。

原则（Prompt 3 §14）：
- Ranking 不交给 LLM“看感觉挑”。全部来自结构化、可测试的规则。
- 分数只使用 candidate 的元数据字段，可解释、可回归。
"""

from __future__ import annotations

from collections import defaultdict

from .domain import MatchReason, SearchIntent
from .evidence import CandidateRecord, SimilarityLink

VERIFIED_STATUSES = {"passed", "program_verified", "teacher_review_approved"}
NEEDS_REVIEW_STATUSES = {"needs_math_review", "needs_formula_review", "teacher_review_required"}

_DUPLICATE_RELATIONS = {"exact_duplicate", "same_problem_different_source", "same_problem_different_solution"}
_DEDUP_MIN_CONFIDENCE = 0.6


def _contains_any(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term and term.lower() in lowered]


def term_matches(record: CandidateRecord, terms: list[str]) -> list[str]:
    haystack = " ".join(
        [
            record.stem,
            record.chapter or "",
            record.section or "",
            record.volume or "",
            " ".join(record.knowledge_points),
        ]
    )
    return _contains_any(haystack, terms)


def difficulty_fit(record: CandidateRecord, intent: SearchIntent) -> tuple[int, str]:
    if intent.difficulty is not None:
        if record.difficulty == intent.difficulty:
            return 15, "difficulty_matched"
        if abs(record.difficulty - intent.difficulty) == 1:
            return 5, "difficulty_adjacent"
        return -20, "difficulty_mismatch"
    if intent.difficulty_range:
        low, high = intent.difficulty_range
        if low <= record.difficulty <= high:
            return 15, "difficulty_matched"
        if abs(record.difficulty - low) == 1 or abs(record.difficulty - high) == 1:
            return 5, "difficulty_adjacent"
        return -20, "difficulty_mismatch"
    return 0, "difficulty_unspecified"


def score_candidate(record: CandidateRecord, intent: SearchIntent) -> tuple[int, list[MatchReason]]:
    reasons: list[MatchReason] = []
    total = 0

    mapped_kp_ids = set(intent.curriculum.knowledge_point_ids)
    if mapped_kp_ids:
        matched = mapped_kp_ids & set(record.knowledge_points)
        if matched:
            total += 40
            reasons.append(MatchReason(code="curriculum_matched", label="匹配教材知识点"))

    kp_terms = [term for term in intent.knowledge_points if term]
    sub_terms = [term for term in intent.sub_knowledge_points if term]
    for term in kp_terms:
        if term_matches(record, [term]):
            total += 25
            reasons.append(MatchReason(code="knowledge_point_matched", label=f"匹配知识点：{term}"))
    for term in sub_terms:
        if term_matches(record, [term]):
            total += 20
            reasons.append(MatchReason(code="sub_knowledge_matched", label=f"匹配：{term}", strength="soft"))

    fit, reason_code = difficulty_fit(record, intent)
    total += fit
    if reason_code == "difficulty_matched":
        label = f"难度符合：{intent.difficulty if intent.difficulty is not None else intent.difficulty_range}"
        reasons.append(MatchReason(code=reason_code, label=label))
    elif reason_code == "difficulty_adjacent":
        reasons.append(MatchReason(code=reason_code, label="难度接近要求", strength="soft"))

    if intent.question_types and record.question_type in intent.question_types:
        total += 10
        reasons.append(MatchReason(code="question_type_matched", label="题型符合要求"))

    if intent.year_from is not None and record.year is not None:
        if intent.year_from <= record.year <= (intent.year_to or intent.year_from):
            total += 10
            reasons.append(MatchReason(code="year_matched", label=f"年份符合：{record.year}"))

    if intent.regions and record.region and record.region in intent.regions:
        total += 10
        reasons.append(MatchReason(code="region_matched", label=f"地区符合：{record.region}"))

    if record.verification_status in VERIFIED_STATUSES:
        total += 15
        reasons.append(MatchReason(code="verification_verified", label="程序验证通过"))
    elif record.verification_status in NEEDS_REVIEW_STATUSES:
        total += 5
        reasons.append(MatchReason(code="verification_review_required", label="需要教师复核"))

    if record.visibility not in ("private", ""):
        total += 5

    return total, reasons


def similarity_clusters(
    records: dict[str, CandidateRecord],
    links: list[SimilarityLink],
    intent: SearchIntent,
) -> dict[str, str]:
    """把被证据标记为重复/变体的题目聚为一组；组名取字典序最小的 question_id。"""
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[max(root_left, root_right)] = min(root_left, root_right)

    for link in links:
        if link.relation not in _DUPLICATE_RELATIONS and link.relation != "variant":
            continue
        if link.confidence < _DEDUP_MIN_CONFIDENCE and link.relation == "variant":
            continue
        left = link.question_id or ""
        right = link.other_question_id or ""
        if left in records and right in records:
            union(left, right)
        elif right in records and left:
            # 锚点不在候选里：只要它出现就归组，便于 exclude_similar 过滤。
            union(right, left)
    clusters: dict[str, str] = {}
    for question_id in list(records) + [link.question_id for link in links if link.question_id]:
        clusters[question_id] = find(question_id)
    for anchor in intent.exclude_similar_to:
        clusters[anchor] = find(anchor)
    return clusters


def deduplicate(
    records: dict[str, CandidateRecord],
    clusters: dict[str, str],
    scores: dict[str, tuple[int, list[MatchReason]]],
) -> list[str]:
    """每组只保留得分最高的一个；返回保留的 question_id 列表。"""
    groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for question_id in records:
        score_reasons = scores.get(question_id)
        if score_reasons is None:
            continue
        groups[clusters.get(question_id, question_id)].append((score_reasons[0], question_id))
    kept: list[str] = []
    for group_id, members in groups.items():
        members.sort(key=lambda item: (-item[0], item[1]))
        kept.append(members[0][1])
    kept.sort(key=lambda qid: (-scores[qid][0], qid))
    return kept


def diverse_select(
    ranked_ids: list[str],
    records: dict[str, CandidateRecord],
    scores: dict[str, int],
    count: int,
) -> list[str]:
    """greedy 多样性选择：在不破坏已排序优先级的前提下，给新题型/新知识点/新难度桶加分。"""
    selected: list[str] = []
    used_types: set[str] = set()
    used_kps: set[str] = set()
    used_diff: set[int] = set()
    remaining = list(ranked_ids)
    while remaining and len(selected) < count:
        best_id = None
        best_effective = -10**9
        for question_id in remaining:
            record = records[question_id]
            bonus = 0
            if record.question_type and record.question_type not in used_types:
                bonus += 6
            new_kps = [kp for kp in record.knowledge_points if kp not in used_kps]
            if new_kps:
                bonus += 6
            if record.difficulty and record.difficulty not in used_diff:
                bonus += 4
            effective = scores[question_id] + bonus
            if effective > best_effective:
                best_effective = effective
                best_id = question_id
        if best_id is None:
            break
        remaining.remove(best_id)
        selected.append(best_id)
        record = records[best_id]
        used_types.add(record.question_type)
        used_kps.update(record.knowledge_points)
        used_diff.add(record.difficulty)
    return selected
