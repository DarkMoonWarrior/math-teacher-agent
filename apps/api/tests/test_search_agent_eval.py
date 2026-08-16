"""Search Agent 离线评估（Prompt 3 §40-43）。

- eval-cases.json 全部由项目自建（synthetic=true），不含真实教师 query / 第三方内容。
- Intent Field Accuracy：确定性解析器逐字段对照产品语义。
- Trust Gate：Fake Question ID / Source Hallucination / Verification Hallucination /
  Hard Silent Violation / Relaxation Disclosure / No-Result Honesty / Duplicate Rate。

强制 Gate（全部必须为 0，任何一项失败即测试失败）：
  Fake Question ID Rate = 0
  Source Hallucination Rate = 0
  Verification Hallucination Rate = 0
  Hard Constraint Silent Violation = 0
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.modules.curriculum import CsvCurriculumCatalog
from app.modules.question_bank import QuestionBank
from app.modules.search_agent.pipeline import SearchAgentPipeline, _satisfies
from app.modules.search_agent.evidence import CandidateRecord
from app.modules.search_agent.ranking import VERIFIED_STATUSES

from tests.test_search_agent_pipeline import (
    FakeRuntime,
    _pipeline,
    _result,
    _search_call,
    _search_item,
    _similar_call,
    _run,
)

_FIXTURES = Path(__file__).resolve().parents[3] / "data" / "test-fixtures" / "search-agent"
_EVAL_CASES = _FIXTURES / "eval-cases.json"
_CURRICULUM_CSV = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "high-school-math-ai"
    / "curriculum"
    / "pep-a-full-knowledge-tree-v1.csv"
)

BANK_TRUTH = {
    "q_sa_focus_01": {"verification_status": "passed", "source_status": "question_content_user_declared_usable"},
    "q_sa_focus_02": {"verification_status": "passed", "source_status": "question_content_user_declared_usable"},
    "q_sa_focus_03": {"verification_status": "passed", "source_status": "question_content_user_declared_usable"},
    "q_sa_ellipse_03": {"verification_status": "passed", "source_status": "question_content_user_declared_usable"},
    "q_sa_ellipse_04": {"verification_status": "passed", "source_status": "question_content_user_declared_usable"},
}


def _load_cases() -> list[dict[str, Any]]:
    payload = json.loads(_EVAL_CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len(cases) >= 40
    return cases


def _check_intent(case: dict[str, Any], intent: Any) -> tuple[int, int, list[str]]:
    """逐字段对照产品语义；返回 (passed, total, failures)。"""
    expected = case["expected"]
    passed = 0
    total = 0
    failures: list[str] = []

    def eq(field: str, actual: Any, want: Any) -> None:
        nonlocal passed, total
        total += 1
        if actual == want:
            passed += 1
        else:
            failures.append(f"{case['id']}.{field}: got={actual!r} want={want!r}")

    if "count" in expected:
        eq("count", intent.count, expected["count"])
    if "requested_count" in expected:
        eq("requested_count", intent.requested_count, expected["requested_count"])
    if "limit_applied" in expected:
        eq("limit_applied", intent.limit_applied, expected["limit_applied"])
    if "grade" in expected:
        eq("grade", intent.grade, expected["grade"])
    if "difficulty" in expected:
        eq("difficulty", intent.difficulty, expected["difficulty"])
    if "difficulty_range" in expected:
        eq("difficulty_range", intent.difficulty_range, expected["difficulty_range"])
    if "question_types" in expected:
        eq("question_types", intent.question_types, expected["question_types"])
    if "regions" in expected:
        eq("regions", intent.regions, expected["regions"])
    if "year_from" in expected:
        eq("year_from", intent.year_from, expected["year_from"])
    if "year_to" in expected:
        eq("year_to", intent.year_to, expected["year_to"])
    if "teaching_usage" in expected:
        eq("teaching_usage", intent.teaching_usage, expected["teaching_usage"])
    if "require_verified" in expected:
        eq("require_verified", intent.require_verified, expected["require_verified"])
    if "allow_related_fallback" in expected:
        eq("allow_related_fallback", intent.allow_related_fallback, expected["allow_related_fallback"])
    if "exclude_question_ids" in expected:
        eq("exclude_question_ids", intent.exclude_question_ids, expected["exclude_question_ids"])
    if "exclude_similar_to" in expected:
        eq("exclude_similar_to", intent.exclude_similar_to, expected["exclude_similar_to"])
    if "volume" in expected:
        eq("volume", intent.volume, expected["volume"])
    if "chapter" in expected:
        eq("chapter", intent.curriculum.chapter, expected["chapter"])
    if "kp_ids_grounded" in expected:
        total += 1
        ok = all(
            node.startswith(("kp_", "pep_a")) for node in intent.curriculum.knowledge_point_ids
        )
        passed += int(ok)
        if not ok:
            failures.append(f"{case['id']}.kp_ids_grounded")
    for term in expected.get("knowledge_points_contains", []):
        total += 1
        pool = intent.knowledge_points + intent.sub_knowledge_points
        if term in pool:
            passed += 1
        else:
            failures.append(f"{case['id']}.knowledge_points_contains[{term}]")
    for term in expected.get("sub_knowledge_points_contains", []):
        total += 1
        if term in intent.sub_knowledge_points:
            passed += 1
        else:
            failures.append(f"{case['id']}.sub_knowledge_points_contains[{term}]")
    for field in expected.get("hard_fields", []):
        total += 1
        if any(constraint.field == field for constraint in intent.hard_constraints()):
            passed += 1
        else:
            failures.append(f"{case['id']}.hard_fields[{field}]")
    for field in expected.get("soft_fields", []):
        total += 1
        if any(constraint.field == field for constraint in intent.soft_constraints()):
            passed += 1
        else:
            failures.append(f"{case['id']}.soft_fields[{field}]")
    return passed, total, failures


def _canned_runtime() -> FakeRuntime:
    """固定证据池：与 query 无关的 canned tool 输出（不硬编码 query→结果 映射）。"""
    return FakeRuntime(_result([
        _search_call([
            # 工具撒谎：verification/source 与业务真值不符，pipeline 必须用真值。
            _search_item("q_sa_focus_01", verification_status="teacher_review_required", source_status="rights_unclear"),
            _search_item("q_sa_focus_02"),
            _search_item("q_sa_focus_03", question_type="fill_blank"),
            _search_item("q_sa_ellipse_03"),
            _search_item("q_sa_ellipse_04"),
            _search_item("q_fake_999"),
        ]),
        _similar_call("q_sa_focus_01", [
            {"question_id": "q_sa_focus_02", "stem": "…", "relation": "exact_duplicate", "confidence": 0.95, "status": "active"},
        ]),
    ]))


def _result_item_satisfies(item: Any, constraint: Any) -> bool:
    record = CandidateRecord(
        question_id=item.question_id,
        stem=item.stem,
        question_type=item.question_type,
        knowledge_points=list(item.knowledge_points),
        difficulty=item.difficulty,
        verification_status=item.verification_status,
        chapter=item.chapter,
        section=item.section,
        volume=item.volume,
        year=item.year,
        region=item.region,
    )
    return _satisfies(record, constraint)


def test_intent_field_accuracy_meets_target(tmp_path: Path) -> None:
    cases = _load_cases()
    bank = QuestionBank(tmp_path / "eval.sqlite3")
    bank.import_batch(_FIXTURES / "search-agent-synthetic-14q-v1.json")
    catalog = CsvCurriculumCatalog(_CURRICULUM_CSV)
    pipeline = SearchAgentPipeline(question_bank=bank, catalog=catalog)

    passed = 0
    total = 0
    failures: list[str] = []
    for case in cases:
        intent = pipeline.parser.parse(case["query"])
        case_passed, case_total, case_failures = _check_intent(case, intent)
        passed += case_passed
        total += case_total
        failures.extend(case_failures)
    accuracy = passed / total if total else 0.0
    print(f"\n[intent] cases={len(cases)} checks={total} passed={passed} accuracy={accuracy:.3f}")
    if failures:
        print("intent failures:")
        for failure in failures[:40]:
            print("  " + failure)
    assert accuracy >= 0.90, f"Intent Field Accuracy {accuracy:.3f} < 0.90"


def test_trust_gates_all_zero(tmp_path: Path) -> None:
    cases = _load_cases()
    bank = QuestionBank(tmp_path / "eval-gates.sqlite3")
    bank.import_batch(_FIXTURES / "search-agent-synthetic-14q-v1.json")
    catalog = CsvCurriculumCatalog(_CURRICULUM_CSV)
    pipeline = _pipeline(bank, catalog, _canned_runtime())

    outcome_cases = [case for case in cases if "outcome" in case.get("expected", {})]
    assert outcome_cases, "eval 集合缺少 outcome 用例"

    fake_ids = 0
    source_hallucinations = 0
    verification_hallucinations = 0
    hard_violations = 0
    hard_checks = 0
    undisclosed_relaxations = 0
    relaxation_events = 0
    dishonest_no_result = 0
    duplicate_pairs = 0
    count_overruns = 0

    for case in outcome_cases:
        response = _run(pipeline.run(case["query"]))
        ids = [item.question_id for item in response.results]
        assert "q_fake_999" not in ids, "Fake Question ID Gate 被突破"
        if response.returned_count > response.requested_count:
            count_overruns += 1
        for item in response.results:
            truth = BANK_TRUTH.get(item.question_id)
            if truth is None:
                fake_ids += 1
                continue
            if item.source_status != truth["source_status"]:
                source_hallucinations += 1
            if item.verification_status != truth["verification_status"]:
                verification_hallucinations += 1
            for constraint in response.intent.hard_constraints():
                if constraint.field in {"exclude_question_ids", "exclude_similar_to", "grade"}:
                    continue
                hard_checks += 1
                if not _result_item_satisfies(item, constraint):
                    hard_violations += 1
        for relaxation in response.relaxations:
            relaxation_events += 1
            if not relaxation.disclosed:
                undisclosed_relaxations += 1
        if case["expected"]["outcome"] == "no_exact_match":
            if response.results or "没有找到完全满足条件" not in response.answer_summary:
                dishonest_no_result += 1
        if case["expected"]["outcome"] == "relaxation_disclosed":
            relaxed_items = [item for item in response.results if item.relaxed_fields]
            if not relaxed_items or not response.relaxations:
                undisclosed_relaxations += 1
        if case["expected"]["outcome"] == "deduplicated":
            pair = {"q_sa_focus_01", "q_sa_focus_02"}
            if pair <= set(ids):
                duplicate_pairs += 1

    print(
        "\n[gates] "
        f"fake_ids={fake_ids} source_hallucinations={source_hallucinations} "
        f"verification_hallucinations={verification_hallucinations} "
        f"hard_violations={hard_violations}/{hard_checks} "
        f"undisclosed_relaxations={undisclosed_relaxations}/{relaxation_events} "
        f"dishonest_no_result={dishonest_no_result} duplicate_pairs={duplicate_pairs} "
        f"count_overruns={count_overruns}"
    )
    assert fake_ids == 0
    assert source_hallucinations == 0
    assert verification_hallucinations == 0
    assert hard_violations == 0
    assert undisclosed_relaxations == 0
    assert dishonest_no_result == 0
    assert duplicate_pairs == 0
    assert count_overruns == 0