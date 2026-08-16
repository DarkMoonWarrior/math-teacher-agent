"""Grounding 防伪门：SearchAgentResponse 的事实字段必须可追溯到 Tool 证据。

Prompt 3 Trust Gate：
- 结果中的每个 question_id 必须来自 Tool 输出，且能通过 Business Service
  再读取校验（get_question 不存在 -> 丢弃）。
- 来源 / 年份 / 地区 / 验证状态只能来自 Business Service，LLM 文本不得补充。
- Assistant 解释文本中出现的未核实 question_id 会被替换为占位提示，
  绝不把模型编造的 ID 展示成真实题目。
"""

from __future__ import annotations

import re
from typing import Any

from .domain import SearchAgentResponse
from .evidence import CandidateRecord, SearchEvidence

# 与 intent_parser._ID_PATTERN 同源：识别疑似 question_id 的 token。
_ID_PATTERN = re.compile(r"[Qq][A-Za-z0-9_-]{2,}")

_UNVERIFIABLE_PLACEHOLDER = "［题目ID无法核实］"


def grounded_question_ids(evidence: SearchEvidence) -> set[str]:
    """只有出现在 Tool 输出中的 question_id 才被视为 grounded。"""
    return evidence.record_ids()


def find_ungrounded_question_ids(text: str, grounded_ids: set[str]) -> list[str]:
    """Assistant 文本中提及、但不在 Tool 证据里的疑似题目 ID。"""
    found: list[str] = []
    for token in _ID_PATTERN.findall(text or ""):
        if token not in grounded_ids and token not in found:
            found.append(token)
    return found


def sanitize_assistant_text(text: str, grounded_ids: set[str]) -> str:
    """把解释文本中未核实的题目 ID 替换为占位提示。

    注意：真实题目的题干 / 选项 / 答案永远只来自 structured results，
    本函数只处理 assistant 的自然语言解释，不允许它冒充题目。
    """
    return _ID_PATTERN.sub(
        lambda match: match.group(0)
        if match.group(0) in grounded_ids
        else _UNVERIFIABLE_PLACEHOLDER,
        text or "",
    )


def validate_response_grounding(
    response: SearchAgentResponse, records: dict[str, CandidateRecord]
) -> list[str]:
    """结构校验：任何 result 必须存在于 grounding 记录中，否则返回错误说明。"""
    errors: list[str] = []
    for item in response.results:
        record = records.get(item.question_id)
        if record is None or not record.enriched:
            errors.append(
                f"result {item.question_id} 未通过 Business Service grounding 校验"
            )
    return errors


def ensure_no_fabricated_fields(response: SearchAgentResponse) -> list[str]:
    """防伪造检查：结果条目不包含未知状态值。"""
    errors: list[str] = []
    allowed_visibility = {"private", "shared", "public", ""}
    for item in response.results:
        if item.visibility not in allowed_visibility:
            errors.append(f"{item.question_id} visibility 非法：{item.visibility}")
        if item.source_status not in {
            "",
            "commercial_granted",
            "public_permissive",
            "question_content_user_declared_usable",
            "rights_unclear",
        }:
            errors.append(f"{item.question_id} source_status 非法：{item.source_status}")
    return errors


def grounding_report(response: SearchAgentResponse, records: dict[str, CandidateRecord]) -> dict[str, Any]:
    return {
        "result_ids_grounded": len(validate_response_grounding(response, records)) == 0,
        "fabricated_field_errors": ensure_no_fabricated_fields(response),
    }
