"""Search Agent Holdout Evaluation（Prompt 3.5 §2-3）。

- holdout-cases.json 全部由项目自建（synthetic=true, source=project_created），
  与原 50 条 eval query 不重复；expected 依据产品语义 + 真实 Curriculum Catalog 编写。
- 第一轮直接记录真实成绩：不因 Holdout 分数修改 SearchIntentParser / ranking。
- Gate：Holdout Intent Field Accuracy >= 0.90；
        Hard Constraint Silent Violation = 0（outcome 用例，pipeline 级）。
- 指标输出：intent_field / hard_soft_interpretation / count / teaching_usage /
  curriculum_mapping 分项准确率。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.modules.curriculum import CsvCurriculumCatalog
from app.modules.question_bank import QuestionBank
from app.modules.search_agent import SearchIntentParser
from app.modules.search_agent.pipeline import SearchAgentPipeline

from tests.test_search_agent_eval import (
    BANK_TRUTH,
    _canned_runtime,
    _check_intent,
    _result_item_satisfies,
)
from tests.test_search_agent_pipeline import (
    _pipeline,
    _run,
)

_FIXTURES = Path(__file__).resolve().parents[3] / "data" / "test-fixtures" / "search-agent"
_HOLDOUT_CASES = _FIXTURES / "holdout-cases.json"
_EVAL_CASES = _FIXTURES / "eval-cases.json"
_CURRICULUM_CSV = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "high-school-math-ai"
    / "curriculum"
    / "pep-a-full-knowledge-tree-v1.csv"
)

# 分项指标对应的 expected 字段（用于逐字段归因，不影响 _check_intent 判定）。
_METRIC_FIELDS = {
    "count": {"count", "requested_count", "limit_applied"},
    "teaching_usage": {"teaching_usage"},
    "curriculum_mapping": {
        "volume", "chapter", "knowledge_points_contains",
        "sub_knowledge_points_contains", "kp_ids_grounded",
    },
    "hard_soft_interpretation": {"hard_fields", "soft_fields"},
}


def _load_holdout_cases() -> list[dict[str, Any]]:
    payload = json.loads(_HOLDOUT_CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len(cases) >= 20
    return cases


def _load_holdout_reference_date() -> date:
    payload = json.loads(_HOLDOUT_CASES.read_text(encoding="utf-8"))
    return date.fromisoformat(payload["reference_date"])


def _load_eval_queries() -> set[str]:
    payload = json.loads(_EVAL_CASES.read_text(encoding="utf-8"))
    return {case["query"] for case in payload["cases"]}


def _check_intent_metrics(case: dict[str, Any], intent: Any) -> dict[str, tuple[int, int, list[str]]]:
    """逐字段核对并做分项归因；整体判定仍复用 _check_intent 的字段语义。

    返回 {metric: (passed, total, failures)}，其中 metric == "intent_field" 为全部字段。
    """
    expected = case["expected"]
    metrics: dict[str, list[tuple[str, int, int]]] = {name: [] for name in _METRIC_FIELDS}
    metrics["intent_field"] = []

    def eq(field: str, actual: Any, want: Any) -> None:
        ok = actual == want
        metrics["intent_field"].append((field, int(ok), 1))
        for name, fields in _METRIC_FIELDS.items():
            if field in fields:
                metrics[name].append((field, int(ok), 1))

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
        ok = all(
            node.startswith(("kp_", "pep_a")) for node in intent.curriculum.knowledge_point_ids
        )
        metrics["intent_field"].append(("kp_ids_grounded", int(ok), 1))
        metrics["curriculum_mapping"].append(("kp_ids_grounded", int(ok), 1))
    for fragment in expected.get("parse_warnings_contains", []):
        ok = any(fragment in warning for warning in intent.parse_warnings)
        metrics["intent_field"].append((f"parse_warnings_contains[{fragment}]", int(ok), 1))
    for term in expected.get("knowledge_points_contains", []):
        ok = term in (intent.knowledge_points + intent.sub_knowledge_points)
        metrics["intent_field"].append((f"knowledge_points_contains[{term}]", int(ok), 1))
        metrics["curriculum_mapping"].append((f"knowledge_points_contains[{term}]", int(ok), 1))
    for term in expected.get("sub_knowledge_points_contains", []):
        ok = term in intent.sub_knowledge_points
        metrics["intent_field"].append((f"sub_knowledge_points_contains[{term}]", int(ok), 1))
        metrics["curriculum_mapping"].append((f"sub_knowledge_points_contains[{term}]", int(ok), 1))
    for field in expected.get("hard_fields", []):
        ok = any(c.field == field for c in intent.hard_constraints())
        metrics["intent_field"].append((f"hard_fields[{field}]", int(ok), 1))
        metrics["hard_soft_interpretation"].append((f"hard_fields[{field}]", int(ok), 1))
    for field in expected.get("soft_fields", []):
        ok = any(c.field == field for c in intent.soft_constraints())
        metrics["intent_field"].append((f"soft_fields[{field}]", int(ok), 1))
        metrics["hard_soft_interpretation"].append((f"soft_fields[{field}]", int(ok), 1))

    return {
        name: (
            sum(item[1] for item in items),
            sum(item[2] for item in items),
            [f"{case['id']}.{item[0]}" for item in items if item[1] == 0],
        )
        for name, items in metrics.items()
    }


def test_holdout_cases_are_fresh_and_distinct() -> None:
    """Holdout 与原 eval 不允许重复 query，且 id 唯一。"""
    cases = _load_holdout_cases()
    eval_queries = _load_eval_queries()
    queries = [case["query"] for case in cases]
    assert len(set(queries)) == len(queries), "holdout query 重复"
    duplicates = sorted(set(queries) & eval_queries)
    assert not duplicates, f"holdout 与原 50 条 eval 重复: {duplicates}"
    ids = [case["id"] for case in cases]
    assert len(set(ids)) == len(ids), "holdout id 重复"


def test_holdout_intent_field_accuracy_meets_target(tmp_path: Path) -> None:
    cases = _load_holdout_cases()
    bank = QuestionBank(tmp_path / "holdout-eval.sqlite3")
    bank.import_batch(_FIXTURES / "search-agent-synthetic-14q-v1.json")
    catalog = CsvCurriculumCatalog(_CURRICULUM_CSV)
    parser = SearchIntentParser(catalog, reference_date=_load_holdout_reference_date())

    # 先冻结实现：_check_intent 与逐字段 metrics 同源，保证与 50 条 eval 判定一致。
    totals: dict[str, list[int]] = {name: [0, 0] for name in _METRIC_FIELDS}
    totals["intent_field"] = [0, 0]
    failures: list[str] = []
    for case in cases:
        intent = parser.parse(case["query"])
        # 整体字段判定（与 eval 同一套 checker）。
        case_passed, case_total, case_failures = _check_intent(case, intent)
        totals["intent_field"][0] += case_passed
        totals["intent_field"][1] += case_total
        failures.extend(case_failures)
        # 分项归因。
        per_metric = _check_intent_metrics(case, intent)
        for name, (passed, total, _) in per_metric.items():
            totals[name][0] += passed
            totals[name][1] += total

    accuracy = totals["intent_field"][0] / totals["intent_field"][1] if totals["intent_field"][1] else 0.0
    print(f"\n[holdout-intent] cases={len(cases)} checks={totals['intent_field'][1]} "
          f"passed={totals['intent_field'][0]} accuracy={accuracy:.3f}")
    for name in ("hard_soft_interpretation", "count", "teaching_usage", "curriculum_mapping"):
        passed, total = totals[name]
        rate = passed / total if total else 0.0
        print(f"  {name}: {passed}/{total} ({rate:.3f})")
    if failures:
        print("holdout intent failures:")
        for failure in failures[:40]:
            print("  " + failure)
    assert accuracy >= 0.90, f"Holdout Intent Field Accuracy {accuracy:.3f} < 0.90"


def test_holdout_trust_gates_all_zero(tmp_path: Path) -> None:
    """outcome 用例的 pipeline 级信任门：fake ID / source / verification / hard / 诚实无结果。"""
    cases = [case for case in _load_holdout_cases() if "outcome" in case.get("expected", {})]
    assert cases, "holdout 集合缺少 outcome 用例"
    bank = QuestionBank(tmp_path / "holdout-gates.sqlite3")
    bank.import_batch(_FIXTURES / "search-agent-synthetic-14q-v1.json")
    catalog = CsvCurriculumCatalog(_CURRICULUM_CSV)
    pipeline = _pipeline(bank, catalog, _canned_runtime())

    fake_ids = 0
    source_hallucinations = 0
    verification_hallucinations = 0
    hard_violations = 0
    hard_checks = 0
    dishonest_no_result = 0
    count_overruns = 0

    for case in cases:
        response = _run(pipeline.run(case["query"]))
        ids = [item.question_id for item in response.results]
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
        if case["expected"]["outcome"] == "no_exact_match":
            if response.results or "没有找到完全满足条件" not in response.answer_summary:
                dishonest_no_result += 1

    print(
        f"\n[holdout-gates] fake_ids={fake_ids} source_hallucinations={source_hallucinations} "
        f"verification_hallucinations={verification_hallucinations} "
        f"hard_violations={hard_violations}/{hard_checks} "
        f"dishonest_no_result={dishonest_no_result} count_overruns={count_overruns}"
    )
    assert fake_ids == 0
    assert source_hallucinations == 0
    assert verification_hallucinations == 0
    assert hard_violations == 0
    assert dishonest_no_result == 0
    assert count_overruns == 0
