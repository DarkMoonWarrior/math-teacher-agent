"""从 Agent Run Result 中提取 grounding 证据。

SearchAgentResponse 的事实字段只能来自两类证据：
1. Tool 调用结果（ToolGateway 返回的 structured JSON）；
2. Business Service 的再读取（QuestionBank.get_question，与 Tool 同一条业务路径）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent_runtime.models import TeacherAgentRunResult

from .domain import SearchIntent


@dataclass
class CandidateRecord:
    question_id: str
    stem: str = ""
    question_type: str = ""
    knowledge_points: list[str] = field(default_factory=list)
    difficulty: int = 0
    verification_status: str = ""
    source_status: str = ""
    visibility: str = ""
    chapter: str | None = None
    section: str | None = None
    volume: str | None = None
    year: int | None = None
    region: str | None = None
    enriched: bool = False


@dataclass
class SimilarityLink:
    question_id: str
    other_question_id: str
    relation: str
    confidence: float


@dataclass
class SearchEvidence:
    records: dict[str, CandidateRecord] = field(default_factory=dict)
    similarity_links: list[SimilarityLink] = field(default_factory=list)
    tool_call_count: int = 0
    search_total: int = 0
    search_truncated: bool = False
    assistant_text: str = ""
    warnings: list[str] = field(default_factory=list)

    def record_ids(self) -> set[str]:
        return set(self.records)


def _text(value: Any) -> str:
    return str(value or "")


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def collect_evidence(run_result: TeacherAgentRunResult) -> SearchEvidence:
    evidence = SearchEvidence(
        tool_call_count=len(run_result.tool_calls),
        assistant_text=run_result.final_text or "",
    )
    for call in run_result.tool_calls:
        output = call.output or {}
        if call.status != "ok" or not isinstance(output, dict):
            continue
        if call.tool_name == "search_questions":
            items = output.get("items") or []
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    question_id = _text(item.get("question_id"))
                    if not question_id:
                        continue
                    record = CandidateRecord(
                        question_id=question_id,
                        stem=_text(item.get("stem")),
                        question_type=_text(item.get("question_type")),
                        knowledge_points=[_text(v) for v in (item.get("knowledge_points") or [])],
                        difficulty=_int_or_none(item.get("difficulty")) or 0,
                        verification_status=_text(item.get("verification_status")),
                        source_status=_text(item.get("source_status")),
                        visibility=_text(item.get("visibility")),
                    )
                    evidence.records.setdefault(question_id, record)
            if isinstance(output.get("total"), int):
                evidence.search_total = max(evidence.search_total, int(output["total"]))
            evidence.search_truncated = evidence.search_truncated or bool(output.get("truncated"))
        elif call.tool_name == "get_question":
            question_id = _text(output.get("question_id"))
            if not question_id:
                continue
            record = evidence.records.get(question_id) or CandidateRecord(question_id=question_id)
            record.stem = _text(output.get("stem")) or record.stem
            record.question_type = _text(output.get("question_type")) or record.question_type
            record.verification_status = _text(output.get("verification_status")) or record.verification_status
            record.source_status = _text(output.get("source_status")) or record.source_status
            record.visibility = _text(output.get("visibility")) or record.visibility
            evidence.records[question_id] = record
        elif call.tool_name == "find_similar_questions":
            items = output.get("items") or []
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    member_id = _text(item.get("question_id"))
                    if not member_id:
                        continue
                    record = evidence.records.get(member_id) or CandidateRecord(
                        question_id=member_id,
                        stem=_text(item.get("stem")),
                    )
                    evidence.records.setdefault(member_id, record)
                    evidence.similarity_links.append(
                        SimilarityLink(
                            question_id=_text(call.input.get("question_id")),
                            other_question_id=member_id,
                            relation=_text(item.get("relation")),
                            confidence=float(item.get("confidence") or 0.0),
                        )
                    )
        elif call.tool_name == "get_curriculum_node":
            pass  # 教材节点证据用于映射校验，不产生题目记录。
        elif call.tool_name == "verify_question":
            pass  # 验证状态以业务再读取为准。
    return evidence
