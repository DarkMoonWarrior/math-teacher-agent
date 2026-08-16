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

# 解释文本中可机械核实的“事实”token：年份与验证状态声明。
# 结构化结果（results）是唯一事实来源；自然语言解释不得携带结果中不存在的事实。
_YEAR_PATTERN = re.compile(r"20\d{2}")
_VERIFIED_CLAIM_PATTERN = re.compile(
    r"(程序验证通过|已通过程序验证|已通过验证|验证通过|通过验证|核实通过|已验证)"
)
_UNVERIFIED_CLAIM_PATTERN = re.compile(
    r"(尚未通过程序验证|尚未通过验证|未通过程序验证|未通过验证|尚未验证|未验证|没验证)"
)

_UNVERIFIABLE_PLACEHOLDER = "［题目ID无法核实］"
_YEAR_PLACEHOLDER = "［年份无法核实］"
_VERIFICATION_PLACEHOLDER = "［验证状态无法核实］"


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


def sanitize_assistant_text(
    text: str,
    grounded_ids: set[str],
    *,
    allowed_years: set[int] | None = None,
    verification_supported: bool | None = None,
) -> str:
    """把解释文本中未核实的内容替换为占位提示。

    - 题目 ID：不在 Tool 证据 / 结构化结果中的疑似 ID -> ［题目ID无法核实］。
    - 年份：提供 allowed_years 时，不在结构化结果年份集合中的 20xx -> ［年份无法核实］。
    - 验证声明：提供 verification_supported 时，
      True（全部结果已通过程序验证）-> 抹掉“未验证”类表述；
      False（存在未验证结果或没有结果）-> 抹掉“已验证 / 验证通过”类表述。

    结构化结果始终是唯一事实来源；本函数只处理 assistant 的自然语言解释，
    不允许它冒充题目或补充结构化结果中不存在的事实。
    """
    result = _ID_PATTERN.sub(
        lambda match: match.group(0)
        if match.group(0) in grounded_ids
        else _UNVERIFIABLE_PLACEHOLDER,
        text or "",
    )
    if allowed_years is not None:
        def _year_repl(match: re.Match[str]) -> str:
            year = int(match.group(0))
            return match.group(0) if year in allowed_years else _YEAR_PLACEHOLDER

        result = _YEAR_PATTERN.sub(_year_repl, result)
    if verification_supported is True:
        result = _UNVERIFIED_CLAIM_PATTERN.sub(_VERIFICATION_PLACEHOLDER, result)
    elif verification_supported is False:
        result = _VERIFIED_CLAIM_PATTERN.sub(_VERIFICATION_PLACEHOLDER, result)
    return result


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
