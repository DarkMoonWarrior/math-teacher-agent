"""SearchAgentPipeline：可信 Search Agent 的核心编排（Prompt 3）。

数据流：
    Teacher Query
        ↓ 确定性解析
    SearchIntent + SearchPlan
        ↓ TeacherAgentRuntime（legacy -> UNSUPPORTED_CAPABILITY；dsh -> Agent Service）
    TeacherAgentRunResult.tool_calls（grounding 证据）
        ↓ QuestionBank.get_question 再读取（Business Service 路径）
    结构化过滤 / 排序 / 去重 / 多样性 / Top N
        ↓
    SearchAgentResponse（全部事实字段 grounded）

不变量：
- LLM 只负责理解需求、选择工具、解释结果，绝不伪造题目。
- hard constraint 永不静默放宽；soft 放宽必须写 relaxations 并在 UI 明示。
- 0 结果时诚实返回 No Exact Match，绝不生成题目补数。
- 只读：本模块不执行任何写操作。
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.agent_runtime import (
    TeacherAgentErrorCode,
    TeacherAgentEvent,
    TeacherAgentEventType,
    TeacherAgentRunRequest,
    TeacherAgentRunResult,
    TeacherAgentRunStatus,
    TeacherAgentRuntime,
    get_teacher_agent_runtime,
)
from app.core.config import get_settings
from app.modules.curriculum import CsvCurriculumCatalog
from app.modules.question_bank import QuestionBank
from app.routes.questions import get_question_bank

from .domain import (
    MatchReason,
    Relaxation,
    SearchAgentResponse,
    SearchAgentResultItem,
    SearchConstraint,
    SearchIntent,
    SearchPlan,
    UnmetConstraint,
)
from .evidence import CandidateRecord, SearchEvidence, collect_evidence
from .grounding import sanitize_assistant_text
from .intent_parser import SearchIntentParser
from .planner import build_search_plan
from .ranking import (
    VERIFIED_STATUSES,
    deduplicate,
    diverse_select,
    score_candidate,
    similarity_clusters,
)

logger = logging.getLogger("math_ai.search_agent")

_MAX_STEMS_PREVIEW = 200

# 这些字段没有记录级元数据支撑，不进入 hard 过滤；在文档中明确说明。
_NON_FILTERABLE_CONSTRAINT_FIELDS = {"grade"}


class SearchAgentPipeline:
    """可测试的核心编排器；runtime / bank 可注入，默认走产品级注册表。"""

    def __init__(
        self,
        *,
        runtime: TeacherAgentRuntime | None = None,
        question_bank: QuestionBank | None = None,
        catalog: CsvCurriculumCatalog | None = None,
    ) -> None:
        self._runtime = runtime
        self._bank = question_bank
        self._catalog = catalog
        self._active_runs: dict[str, TeacherAgentRuntime] = {}

    @property
    def runtime(self) -> TeacherAgentRuntime:
        return self._runtime or get_teacher_agent_runtime()

    @property
    def bank(self) -> QuestionBank:
        return self._bank or get_question_bank()

    @property
    def catalog(self) -> CsvCurriculumCatalog:
        if self._catalog is None:
            self._catalog = CsvCurriculumCatalog(get_settings().curriculum_csv)
        return self._catalog

    @property
    def parser(self) -> SearchIntentParser:
        return SearchIntentParser(self.catalog)

    # -- run --------------------------------------------------------------

    async def run(
        self,
        raw_query: str,
        *,
        session_id: str | None = None,
        request_id: str = "",
    ) -> SearchAgentResponse:
        started = time.monotonic()
        request_id = request_id or f"req_{uuid.uuid4().hex}"
        intent = self.parser.parse(raw_query)
        plan = build_search_plan(intent)

        runtime = self.runtime
        if runtime.runtime_name == "legacy":
            return self._error_response(
                request_id=request_id,
                session_id=session_id or "",
                intent=intent,
                plan=plan,
                error_code=TeacherAgentErrorCode.UNSUPPORTED_CAPABILITY,
                message="当前 Agent Runtime（legacy）不支持搜索编排；请配置 MATH_AI_AGENT_RUNTIME=dsh 并启动 Agent Service。",
            )

        message = self._compose_agent_message(intent)
        try:
            run_result = await runtime.run(
                TeacherAgentRunRequest(
                    user_message=message,
                    session_id=session_id,
                    request_id=request_id,
                )
            )
        except Exception as exc:  # pragma: no cover - 防御边界
            logger.exception("search_agent_runtime_raised", extra={"request_id": request_id})
            return self._error_response(
                request_id=request_id,
                session_id=session_id or "",
                intent=intent,
                plan=plan,
                error_code=TeacherAgentErrorCode.INTERNAL_ERROR,
                message=f"Agent Runtime 异常：{type(exc).__name__}",
            )

        self._active_runs[run_result.run_id] = runtime
        if run_result.status == TeacherAgentRunStatus.CANCELLED:
            response = self._error_response(
                request_id=request_id,
                session_id=run_result.session_id,
                intent=intent,
                plan=plan,
                error_code=TeacherAgentErrorCode.RUN_CANCELLED,
                message="搜索已取消",
                run_id=run_result.run_id,
            )
            response.status = "cancelled"
            return response
        if run_result.status == TeacherAgentRunStatus.FAILED:
            error = run_result.error
            code = error.code if error else TeacherAgentErrorCode.INTERNAL_ERROR
            message = error.message if error else "Agent run 失败"
            return self._error_response(
                request_id=request_id,
                session_id=run_result.session_id,
                intent=intent,
                plan=plan,
                error_code=code,
                message=message,
                run_id=run_result.run_id,
            )

        response = self._build_response(
            run_result=run_result,
            intent=intent,
            plan=plan,
            request_id=request_id,
        )
        response.duration_ms = int((time.monotonic() - started) * 1000)
        return response

    # -- stream（SSE） ------------------------------------------------------

    async def stream(
        self,
        raw_query: str,
        *,
        session_id: str | None = None,
        request_id: str = "",
    ) -> AsyncIterator[TeacherAgentEvent]:
        """SSE 友好的流式入口。

        先发出 RUN_STARTED（含 intent/plan 摘要），随后等待 runtime run 完成，
        终态事件携带完整 grounded SearchAgentResponse（前端只读结构化字段）。
        """
        request_id = request_id or f"req_{uuid.uuid4().hex}"
        intent = self.parser.parse(raw_query)
        plan = build_search_plan(intent)
        runtime = self.runtime

        yield TeacherAgentEvent(
            type=TeacherAgentEventType.RUN_STARTED,
            run_id="",
            session_id=session_id or "",
            request_id=request_id,
            data={
                "intent_summary": plan.intent_summary,
                "applied_filters": plan.applied_filters,
                "soft_preferences": plan.soft_preferences,
            },
        )

        if runtime.runtime_name == "legacy":
            yield TeacherAgentEvent(
                type=TeacherAgentEventType.RUN_FAILED,
                run_id="",
                session_id=session_id or "",
                request_id=request_id,
                data={
                    "error": {
                        "code": TeacherAgentErrorCode.UNSUPPORTED_CAPABILITY.value,
                        "message": "当前 Agent Runtime（legacy）不支持搜索编排",
                        "request_id": request_id,
                    }
                },
            )
            return

        run_result = await runtime.run(
            TeacherAgentRunRequest(
                user_message=self._compose_agent_message(intent),
                session_id=session_id,
                request_id=request_id,
            )
        )
        self._active_runs[run_result.run_id] = runtime

        if run_result.status == TeacherAgentRunStatus.CANCELLED:
            yield TeacherAgentEvent(
                type=TeacherAgentEventType.RUN_CANCELLED,
                run_id=run_result.run_id,
                session_id=run_result.session_id,
                request_id=request_id,
                data={
                    "error": {
                        "code": TeacherAgentErrorCode.RUN_CANCELLED.value,
                        "message": "搜索已取消",
                        "request_id": request_id,
                    }
                },
            )
            return
        if run_result.status == TeacherAgentRunStatus.FAILED:
            error = run_result.error
            yield TeacherAgentEvent(
                type=TeacherAgentEventType.RUN_FAILED,
                run_id=run_result.run_id,
                session_id=run_result.session_id,
                request_id=request_id,
                data={
                    "error": (
                        error.model_dump(mode="json")
                        if error
                        else {
                            "code": TeacherAgentErrorCode.INTERNAL_ERROR.value,
                            "message": "Agent run 失败",
                            "request_id": request_id,
                        }
                    )
                },
            )
            return

        response = self._build_response(
            run_result=run_result, intent=intent, plan=plan, request_id=request_id
        )
        yield TeacherAgentEvent(
            type=TeacherAgentEventType.RUN_COMPLETED,
            run_id=run_result.run_id,
            session_id=run_result.session_id,
            request_id=request_id,
            data={"search_response": response.model_dump(mode="json")},
        )

    # -- cancel -------------------------------------------------------------

    async def cancel(self, run_id: str) -> dict[str, Any]:
        runtime = self._active_runs.get(run_id)
        if runtime is None:
            return {
                "run_id": run_id,
                "status": "failed",
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": "未知或已结束的 run_id",
                    "request_id": "",
                },
            }
        result = await runtime.cancel(run_id)
        return {
            "run_id": run_id,
            "status": result.status.value,
            "error": result.error.model_dump(mode="json") if result.error else None,
        }

    # -- 核心构建 -----------------------------------------------------------

    def _compose_agent_message(self, intent: SearchIntent) -> str:
        structured = {
            "grade": intent.grade,
            "volume": intent.volume,
            "chapter": intent.curriculum.chapter,
            "knowledge_point_ids": intent.curriculum.knowledge_point_ids,
            "knowledge_points": intent.knowledge_points,
            "sub_knowledge_points": intent.sub_knowledge_points,
            "question_types": intent.question_types,
            "difficulty": intent.difficulty or intent.difficulty_range,
            "count": intent.count,
            "year_from": intent.year_from,
            "year_to": intent.year_to,
            "regions": intent.regions,
            "teaching_usage": intent.teaching_usage,
            "exclude_question_ids": intent.exclude_question_ids,
            "exclude_similar_to": intent.exclude_similar_to,
            "require_verified": intent.require_verified,
            "hard_constraints": [
                {"field": c.field, "value": c.value} for c in intent.hard_constraints()
            ],
            "soft_constraints": [
                {"field": c.field, "value": c.value} for c in intent.soft_constraints()
            ],
        }
        return (
            "请根据高中数学教师的下列搜题需求调用只读工具完成检索。\n"
            f"教师原始需求：{intent.raw_query}\n"
            "系统解析出的结构化意图（供选择工具参数参考，事实以工具返回结果为准）：\n"
            f"{structured}\n"
            "硬性规则：只能从工具返回结果获得题目；禁止编造 question_id、题干、来源、年份、"
            "地区或验证状态；结果不足时如实说明，不得虚构题目补足数量；hard 条件不得放宽；"
            "不执行任何写操作；不要调用本需求无关的工具。"
        )

    def _error_response(
        self,
        *,
        request_id: str,
        session_id: str,
        intent: SearchIntent,
        plan: SearchPlan,
        error_code: TeacherAgentErrorCode,
        message: str,
        run_id: str = "",
    ) -> SearchAgentResponse:
        return SearchAgentResponse(
            request_id=request_id,
            session_id=session_id,
            run_id=run_id,
            raw_query=intent.raw_query,
            status="error",
            intent=intent,
            plan_summary=plan,
            requested_count=intent.count,
            error={
                "code": error_code.value,
                "message": message,
                "request_id": request_id,
            },
            answer_summary="搜索未完成：Agent Runtime 返回错误。",
            warnings=list(intent.parse_warnings),
        )

    def _ground_records(self, evidence: SearchEvidence) -> dict[str, CandidateRecord]:
        """再读取校验：Tool 输出中的每个 ID 都必须通过 Business Service 校验。

        不存在的 ID（模型编造 / 幻觉）直接丢弃；removed 或不符合 teacher
        usage scope 的题目也被业务门禁排除。所有事实字段以 bank 为准。
        """
        records: dict[str, CandidateRecord] = {}
        for question_id, record in evidence.records.items():
            try:
                detail = self.bank.get_question(question_id)
            except Exception:  # 业务读取失败 -> 保守丢弃
                evidence.warnings.append(f"题目 {question_id} 无法通过业务服务校验，已排除。")
                continue
            if getattr(detail, "library_state", "active") == "removed":
                continue
            if not self._teacher_scope_ok(detail):
                continue
            record.question_id = detail.question_id
            record.stem = detail.stem_plain
            record.question_type = detail.question_type
            record.knowledge_points = list(detail.knowledge_point_ids)
            record.difficulty = int(detail.difficulty)
            record.verification_status = detail.verification_status
            record.source_status = detail.license_status
            record.visibility = detail.visibility
            record.chapter = detail.chapter
            record.section = detail.section
            record.volume = detail.volume
            exam = (detail.raw or {}).get("exam") or {}
            record.year = _int_or_none(exam.get("year"))
            region = exam.get("region")
            record.region = str(region) if region else None
            record.enriched = True
            records[question_id] = record
        return records

    @staticmethod
    def _teacher_scope_ok(detail: Any) -> bool:
        """与 internal gateway 的 teacher usage scope 保持一致（防御性复查）。"""
        status = getattr(detail, "verification_status", "")
        question_id = getattr(detail, "question_id", "")
        if question_id.startswith("q_variant_"):
            return True
        return status == "passed"

    def _filter_excludes(
        self,
        records: dict[str, CandidateRecord],
        evidence: SearchEvidence,
        intent: SearchIntent,
    ) -> dict[str, CandidateRecord]:
        excluded_ids = set(intent.exclude_question_ids)
        filtered = {
            qid: record for qid, record in records.items() if qid not in excluded_ids
        }
        if intent.exclude_similar_to:
            clusters = similarity_clusters(filtered, evidence.similarity_links, intent)
            anchor_roots = {clusters.get(anchor, anchor) for anchor in intent.exclude_similar_to}
            filtered = {
                qid: record
                for qid, record in filtered.items()
                if clusters.get(qid, qid) not in anchor_roots
            }
        return filtered

    def _build_response(
        self,
        *,
        run_result: TeacherAgentRunResult,
        intent: SearchIntent,
        plan: SearchPlan,
        request_id: str,
    ) -> SearchAgentResponse:
        evidence = collect_evidence(run_result)
        records = self._ground_records(evidence)
        records = self._filter_excludes(records, evidence, intent)

        hard_constraints = [
            c
            for c in intent.hard_constraints()
            if c.field not in {"exclude_question_ids", "exclude_similar_to"}
            and c.field not in _NON_FILTERABLE_CONSTRAINT_FIELDS
        ]
        soft_kp_constraints = [
            c
            for c in intent.soft_constraints()
            if c.field == "knowledge_points"
        ]

        eligible = {
            qid: record
            for qid, record in records.items()
            if all(_satisfies(record, constraint) for constraint in hard_constraints)
        }
        exact_pool = {
            qid: record
            for qid, record in eligible.items()
            if all(_satisfies(record, constraint) for constraint in soft_kp_constraints)
        }
        fallback_pool = {
            qid: record for qid, record in eligible.items() if qid not in exact_pool
        }

        scores = {qid: score_candidate(record, intent) for qid, record in eligible.items()}
        clusters = similarity_clusters(records, evidence.similarity_links, intent)
        exact_ranked = deduplicate(exact_pool, clusters, scores)
        fallback_ranked = deduplicate(fallback_pool, clusters, scores)

        relaxed_allowed = intent.allow_related_fallback or bool(soft_kp_constraints)
        relaxed_allowed = relaxed_allowed and bool(exact_pool)  # 0 exact 时不硬凑

        selected_ids: list[str] = []
        relaxed_flags: dict[str, list[str]] = {}
        if exact_ranked:
            selected_ids = diverse_select(
                exact_ranked, eligible, {qid: scores[qid][0] for qid in eligible}, intent.count
            )
        if len(selected_ids) < intent.count and relaxed_allowed and fallback_ranked:
            selected_clusters = {clusters.get(qid, qid) for qid in selected_ids}
            candidates = [
                qid
                for qid in fallback_ranked
                if clusters.get(qid, qid) not in selected_clusters
            ]
            extra = diverse_select(
                candidates,
                eligible,
                {qid: scores[qid][0] for qid in eligible},
                intent.count - len(selected_ids),
            )
            for qid in extra:
                relaxed_flags[qid] = ["knowledge_points"]
            selected_ids.extend(extra)

        # 逐条 hard constraint 的满足统计（不静默放宽）。
        unmet_constraints: list[UnmetConstraint] = []
        for constraint in hard_constraints:
            matched_count = sum(
                1 for qid in eligible if _satisfies(eligible[qid], constraint)
            )
            if matched_count < intent.count:
                unmet_constraints.append(
                    UnmetConstraint(
                        field=constraint.field,
                        requested=constraint.value,
                        matched_count=matched_count,
                        reason="满足该条件的候选题目不足",
                    )
                )

        relaxations: list[Relaxation] = []
        if relaxed_flags:
            for constraint in soft_kp_constraints:
                relaxations.append(
                    Relaxation(
                        field=constraint.field,
                        from_value=constraint.value,
                        to_value=None,
                        reason="insufficient_candidates",
                        disclosed=True,
                    )
                )

        results: list[SearchAgentResultItem] = []
        for qid in selected_ids:
            record = eligible[qid]
            reasons = scores[qid][1]
            if qid in relaxed_flags:
                reasons = reasons + [
                    MatchReason(code="soft_relaxed", label="相近知识点补充", strength="soft")
                ]
            results.append(
                SearchAgentResultItem(
                    question_id=qid,
                    stem=record.stem,
                    stem_preview=record.stem[:_MAX_STEMS_PREVIEW],
                    question_type=record.question_type,
                    knowledge_points=record.knowledge_points,
                    difficulty=record.difficulty,
                    verification_status=record.verification_status,
                    source_status=record.source_status,
                    visibility=record.visibility,
                    chapter=record.chapter,
                    section=record.section,
                    volume=record.volume,
                    year=record.year,
                    region=record.region,
                    match_reasons=reasons,
                    relaxed_fields=relaxed_flags.get(qid, []),
                    similarity_group=clusters.get(qid, qid),
                    grounded=True,
                )
            )

        exact_match_count = sum(1 for qid in selected_ids if qid not in relaxed_flags)
        exact_match = exact_match_count >= intent.count
        returned_count = len(results)

        if returned_count == 0:
            answer_summary = "没有找到完全满足条件的题目。可以尝试放宽难度、年份或地区等条件后重新搜索。"
            confidence = "low"
        elif exact_match:
            answer_summary = f"找到 {returned_count} 道题目，全部满足检索条件。"
            confidence = "high"
        else:
            confidence = "medium"
            if relaxed_flags:
                answer_summary = (
                    f"找到 {returned_count} 道题目，其中 {exact_match_count} 道完全满足条件，"
                    f"{len(relaxed_flags)} 道为相近知识点补充。"
                )
            else:
                answer_summary = (
                    f"只找到 {returned_count} 道完全满足条件的题目，未能达到请求数量。"
                )

        suggestions = self._build_suggestions(intent, returned_count, exact_match)

        plan = self._finalize_plan(
            plan,
            intent=intent,
            evidence=evidence,
            candidate_count=len(eligible),
            selected_count=returned_count,
            relaxations=relaxations,
            unmet_constraints=unmet_constraints,
        )

        grounded_ids = evidence.record_ids() & set(records)
        # 解释文本消毒：结构化结果（records）是唯一事实来源。年份与验证状态
        # 声明只有在结果实际支持时才允许出现在 assistant 解释中。
        allowed_years = {record.year for record in records.values() if record.year}
        verification_supported = bool(records) and all(
            record.verification_status in VERIFIED_STATUSES for record in records.values()
        )
        warnings = list(intent.parse_warnings) + list(evidence.warnings)

        return SearchAgentResponse(
            request_id=request_id,
            session_id=run_result.session_id,
            run_id=run_result.run_id,
            raw_query=intent.raw_query,
            status="ok",
            intent=intent,
            plan_summary=plan,
            results=results,
            requested_count=intent.count,
            effective_count=min(intent.count, len(eligible)),
            returned_count=returned_count,
            exact_match_count=exact_match_count,
            exact_match=exact_match,
            relaxations=relaxations,
            unmet_constraints=unmet_constraints,
            warnings=warnings,
            answer_summary=answer_summary,
            assistant_explanation=sanitize_assistant_text(
                run_result.final_text,
                grounded_ids,
                allowed_years=allowed_years or None,
                verification_supported=verification_supported,
            ),
            search_confidence=confidence,
            suggestions=suggestions,
            tool_call_count=evidence.tool_call_count,
            candidate_count=len(eligible),
        )

    def _build_suggestions(
        self, intent: SearchIntent, returned_count: int, exact_match: bool
    ) -> list[str]:
        if returned_count > 0 and exact_match:
            return []
        suggestions: list[str] = []
        if intent.difficulty is not None or intent.difficulty_range:
            suggestions.append("放宽难度范围")
        if intent.year_from is not None:
            suggestions.append("放宽年份范围")
        if intent.regions:
            suggestions.append("放宽地区限制")
        if intent.knowledge_points or intent.sub_knowledge_points:
            suggestions.append("查看相近知识点题目")
        if not suggestions:
            suggestions.append("更换或简化检索关键词")
        return suggestions

    def _finalize_plan(
        self,
        plan: SearchPlan,
        *,
        intent: SearchIntent,
        evidence: SearchEvidence,
        candidate_count: int,
        selected_count: int,
        relaxations: list[Relaxation],
        unmet_constraints: list[UnmetConstraint],
    ) -> SearchPlan:
        statuses = {
            "resolve_curriculum": "completed" if intent.curriculum.knowledge_point_ids else "skipped",
            "apply_hard_filters": "completed",
            "search_candidates": "completed",
            "apply_rights_publication_visibility_gate": "completed",
            "verification_enrichment": "completed" if intent.require_verified else "skipped",
            "deduplicate": "completed" if intent.deduplicate else "skipped",
            "similarity_diversity": "completed" if intent.diversify else "skipped",
            "difficulty_knowledge_rerank": "completed",
            "select_top_n": "completed",
            "generate_explanation": "completed",
        }
        for step in plan.steps:
            step.status = statuses.get(step.title, "pending")  # type: ignore[arg-type]
        plan.candidate_count = candidate_count
        plan.selected_count = selected_count
        plan.relaxations = [item.model_dump(mode="json") for item in relaxations]
        plan.soft_preferences = [
            f"{c.field}={c.value}" for c in intent.soft_constraints()
        ]
        plan.applied_filters["tool_call_count"] = evidence.tool_call_count
        plan.applied_filters["unmet_constraints"] = [
            item.model_dump(mode="json") for item in unmet_constraints
        ]
        return plan


def _satisfies(record: CandidateRecord, constraint: SearchConstraint) -> bool:
    field = constraint.field
    value = constraint.value
    if field == "knowledge_points":
        if isinstance(value, list):
            if not value:
                return True
            if all(isinstance(item, str) for item in value):
                if all(item.startswith("kp_") for item in value):
                    return bool(set(value) & set(record.knowledge_points))
                return any(
                    item and _term_in_record(record, item) for item in value
                )
            return True
        return _term_in_record(record, str(value)) if value else True
    if field == "difficulty":
        return record.difficulty == int(value)
    if field == "difficulty_range":
        low, high = value
        return low <= record.difficulty <= high
    if field == "question_types":
        return record.question_type in value
    if field == "year":
        low, high = value
        if record.year is None:
            return False
        return low <= record.year <= high
    if field == "regions":
        return bool(record.region and record.region in value)
    if field == "volume":
        return record.volume == value
    if field == "chapter":
        return bool(value and record.chapter and value in record.chapter)
    if field == "require_verified":
        return record.verification_status in VERIFIED_STATUSES
    if field == "teaching_usage":
        return True  # 教学用途是排序偏好，不作为过滤条件
    return True


def _term_in_record(record: CandidateRecord, term: str) -> bool:
    if not term:
        return False
    haystack = " ".join(
        [
            record.stem,
            record.chapter or "",
            record.section or "",
            record.volume or "",
            " ".join(record.knowledge_points),
        ]
    )
    return term in haystack


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
