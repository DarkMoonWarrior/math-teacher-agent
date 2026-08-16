"""SearchIntentParser：确定性意图解析。

设计原则：
- LLM 不是解析器。本模块用可测试的规则 + 真实 Curriculum Catalog 完成解析，
  保证 Intent Accuracy 可以离线测量、可回归。
- 教材 / 章节 / 知识点映射只能来自 Curriculum Catalog 的真实 node_id，
  绝不凭“记忆”臆造教材位置。
- 典型中文表达分类：
    只要 / 必须 / 限定 / 不要 / 排除 / 仅 / 只  -> hard
    最好 / 优先 / 尽量 / 偏向 / 相近也行       -> soft
    未提供字段                                  -> default / null
"""

from __future__ import annotations

import re
from typing import Any

from app.modules.curriculum.catalog import InMemoryCurriculumCatalog

from .domain import (
    CurriculumMapping,
    CurriculumNodeRef,
    SearchConstraint,
    SearchIntent,
    SEARCH_DEFAULT_COUNT,
    SEARCH_HARD_MAX_COUNT,
)

HARD_MARKERS = (
    "只要",
    "必须",
    "一定要",
    "只能",
    "仅要",
    "仅限",
    "限定",
    "严格",
    "不要",
    "排除",
    "避开",
    "只收",
    "只找",
)
SOFT_MARKERS = (
    "最好",
    "优先",
    "尽量",
    "偏向",
    "偏好",
    "如果可能",
    "如果有",
    "没有的话",
    "相近",
    "类似",
    "也行",
    "也可以",
    "实在没有",
    "优先考虑",
)

_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_COUNT_PATTERN = re.compile(r"(\d+|[一二两三四五六七八九十]+)\s*[道题个]")
_YEAR_RANGE_PATTERN = re.compile(r"(20[0-2]\d)\s*年?\s*(?:-|到|至)\s*(20[0-2]\d)\s*年?")
_YEAR_SINGLE_PATTERN = re.compile(r"(20[0-2]\d)\s*年?")
_ID_PATTERN = re.compile(r"[Qq][A-Za-z0-9_-]{2,}")

_DIFFICULTY_WORDS: list[tuple[str, int | None, list[int] | None]] = [
    ("压轴", 5, None),
    ("较难", 4, None),
    ("偏难", 4, None),
    ("中等偏难", None, [3, 4]),
    ("中高档", None, [3, 4]),
    ("中等难度", 3, None),
    ("中等", 3, None),
    ("适中", 3, None),
    ("中档", 3, None),
    ("基础", 1, None),
    ("简单", 1, None),
    ("容易", 1, None),
    ("入门", 1, None),
    ("不难", None, [1, 2]),
    ("难", 5, None),
]
_DIFFICULTY_WORDS.sort(key=lambda item: -len(item[0]))

_QUESTION_TYPES = [
    ("多选题", "multiple_choice"),
    ("选择题", "single_choice"),
    ("单选题", "single_choice"),
    ("填空题", "fill_blank"),
    ("解答题", "solution"),
    ("证明题", "proof"),
    ("大题", "solution"),
    ("应用题", "application"),
]
_QUESTION_TYPES.sort(key=lambda item: -len(item[0]))

_REGIONS = [
    ("新高考一卷", "新高考Ⅰ卷"),
    ("新高考二卷", "新高考Ⅱ卷"),
    ("新高考1卷", "新高考Ⅰ卷"),
    ("新高考2卷", "新高考Ⅱ卷"),
    ("全国一卷", "全国Ⅰ卷"),
    ("全国二卷", "全国Ⅱ卷"),
    ("全国甲卷", "全国甲卷"),
    ("全国乙卷", "全国乙卷"),
    ("江苏", "江苏"),
    ("浙江", "浙江"),
    ("上海", "上海"),
    ("北京", "北京"),
    ("天津", "天津"),
    ("山东", "山东"),
    ("广东", "广东"),
    ("湖北", "湖北"),
    ("湖南", "湖南"),
    ("河北", "河北"),
    ("福建", "福建"),
    ("安徽", "安徽"),
    ("四川", "四川"),
    ("重庆", "重庆"),
]
_REGIONS.sort(key=lambda item: -len(item[0]))

_USAGE_WORDS: list[tuple[str, str]] = [
    ("课堂例题", "classroom_example"),
    ("课堂讲解", "classroom_example"),
    ("课堂示范", "classroom_example"),
    ("板书例题", "classroom_example"),
    ("随堂练习", "in_class_practice"),
    ("当堂练习", "in_class_practice"),
    ("当堂训练", "in_class_practice"),
    ("课后练习", "homework"),
    ("课后作业", "homework"),
    ("家庭作业", "homework"),
    ("作业", "homework"),
    ("期末复习", "exam_review"),
    ("期中复习", "exam_review"),
    ("复习课", "exam_review"),
    ("备考", "exam_review"),
    ("摸底", "diagnostic"),
    ("诊断", "diagnostic"),
    ("热身", "warm_up"),
    ("导入", "warm_up"),
    ("引入", "warm_up"),
    ("培优", "challenge"),
    ("挑战", "challenge"),
    ("竞赛", "challenge"),
    ("拔高", "challenge"),
]
_USAGE_WORDS.sort(key=lambda item: -len(item[0]))

_GRADES = [("高一", "高一"), ("高二", "高二"), ("高三", "高三")]
_VOLUMES = [
    ("选择性必修第一册", "选择性必修第一册"),
    ("选择性必修第二册", "选择性必修第二册"),
    ("选择性必修第三册", "选择性必修第三册"),
    ("必修第一册", "必修第一册"),
    ("必修第二册", "必修第二册"),
    ("必修一", "必修第一册"),
    ("必修二", "必修第二册"),
    ("选必一", "选择性必修第一册"),
    ("选必二", "选择性必修第二册"),
    ("选必三", "选择性必修第三册"),
]
_VOLUMES.sort(key=lambda item: -len(item[0]))

# 常见子知识点 / 解题方法词：不映射教材节点，保留为教师表述的子知识点。
_SUB_KNOWLEDGE_TERMS = [
    "构造函数", "焦点弦", "参变分离", "参变量分离", "换元", "数形结合", "分类讨论",
    "放缩", "齐次化", "设点法", "点差法", "弦长公式", "离心率", "极值", "单调性",
    "最值", "零点", "渐近线", "准线", "通径", "切线", "切点", "定点定值", "轨迹方程",
]

# 常用章节/主题词：先于 n-gram 匹配，避免碎片匹配。
_COMMON_CHAPTER_TERMS = [
    "集合", "函数", "指数函数", "对数函数", "三角函数", "数列",
    "不等式", "平面向量", "复数", "立体几何", "空间向量", "解析几何",
    "直线与圆", "圆锥曲线", "椭圆", "双曲线", "抛物线", "导数",
    "概率", "统计", "计数原理", "随机变量", "焦点弦",
]
_COMMON_CHAPTER_TERMS.sort(key=len, reverse=True)


def _split_clauses(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,，。；;、]+", text) if part.strip()]


def _clause_strength(text: str) -> str:
    if any(marker in text for marker in HARD_MARKERS):
        return "hard"
    if any(marker in text for marker in SOFT_MARKERS):
        return "soft"
    return "explicit"


def _strength_for_word(clauses: list[str], word: str) -> str:
    for clause in clauses:
        if word in clause:
            return _clause_strength(clause)
    return "explicit"


def _parse_count(text: str) -> tuple[int | None, bool]:
    matches = list(_COUNT_PATTERN.finditer(text))
    if not matches:
        return None, False
    raw = matches[0].group(1)
    if raw.isdigit():
        number = int(raw)
    else:
        number = sum(_CN_NUM.get(char, 0) for char in raw)
    if number <= 0:
        return None, False
    return min(number, SEARCH_HARD_MAX_COUNT), number > SEARCH_HARD_MAX_COUNT


def _parse_years(text: str) -> tuple[int | None, int | None]:
    range_match = _YEAR_RANGE_PATTERN.search(text)
    if range_match:
        first, second = int(range_match.group(1)), int(range_match.group(2))
        return min(first, second), max(first, second)
    single = _YEAR_SINGLE_PATTERN.search(text)
    if single:
        year = int(single.group(1))
        return year, year
    return None, None


def _parse_difficulty(text: str) -> tuple[int | None, list[int], str]:
    for word, value, value_range in _DIFFICULTY_WORDS:
        if word in text:
            return value, list(value_range or []), word
    return None, [], ""


def _parse_question_types(text: str) -> list[str]:
    found: list[str] = []
    for word, mapped in _QUESTION_TYPES:
        if word in text and mapped not in found:
            # “多选题”比“选择题”长，先匹配；避免把多选题重复计为单选。
            if mapped == "single_choice" and "多选" in text:
                continue
            found.append(mapped)
    return found


def _parse_regions(text: str) -> list[str]:
    found: list[str] = []
    for word, mapped in _REGIONS:
        if word in text and mapped not in found:
            found.append(mapped)
    return found


def _parse_usage(text: str) -> str | None:
    for word, mapped in _USAGE_WORDS:
        if word in text:
            return mapped
    return None


def _parse_exclude_ids(text: str) -> list[str]:
    return list(dict.fromkeys(_ID_PATTERN.findall(text)))


class SearchIntentParser:
    """确定性 SearchIntent 解析器；catalog 传入时做真实教材映射。"""

    def __init__(self, catalog: InMemoryCurriculumCatalog | None = None) -> None:
        self._catalog = catalog
        # term -> 候选 node_id 集合：只索引真实 catalog 名称片段，绝不臆造。
        self._term_index: dict[str, list[str]] = {}
        if catalog is not None:
            try:
                for node in catalog.list_nodes():
                    names = [node.name]
                    names.extend(part for part in re.split(r"[与和及的、]", node.name) if len(part) >= 2)
                    for name in dict.fromkeys(names):
                        self._term_index.setdefault(name, []).append(node.node_id)
                        self._term_index.setdefault(name.lower(), []).append(node.node_id)
            except Exception:
                self._term_index = {}

    def parse(self, raw_query: str) -> SearchIntent:
        text = raw_query.strip()
        clauses = _split_clauses(text)
        constraints: list[SearchConstraint] = []
        warnings: list[str] = []

        requested_count, limit_applied = _parse_count(text)
        count = requested_count if requested_count is not None else SEARCH_DEFAULT_COUNT
        if limit_applied:
            warnings.append(f"单次最多返回 {SEARCH_HARD_MAX_COUNT} 道，请求数量已按上限处理。")

        grade = next((mapped for word, mapped in _GRADES if word in text), None)
        volume = next((mapped for word, mapped in _VOLUMES if word in text), None)
        difficulty, difficulty_range, difficulty_word = _parse_difficulty(text)
        question_types = _parse_question_types(text)
        regions = _parse_regions(text)
        usage = _parse_usage(text)
        year_from, year_to = _parse_years(text)
        exclude_ids = _parse_exclude_ids(text)

        require_verified = any(
            marker in text
            for marker in ("验证过", "已验证", "核实过", "只要验证过的", "程序验证通过")
        )
        allow_related = any(
            marker in text for marker in ("相近", "类似", "也行", "也可以", "没有的话", "实在没有")
        )

        exclude_similar: list[str] = []
        for clause in clauses:
            if any(marker in clause for marker in ("太像", "很像", "相似", "雷同")):
                exclude_similar.extend(_parse_exclude_ids(clause))
        if "排除" in text or "避开" in text:
            exclude_similar.extend(_parse_exclude_ids(text))
        exclude_similar = list(dict.fromkeys(exclude_similar))

        # 教材映射：只来自 catalog 的真实节点。
        mapping = self._map_curriculum(text, clauses)
        if volume:
            mapping.volume = volume

        knowledge_points: list[str] = []
        sub_knowledge_points: list[str] = []
        mapped_names = set(mapping.knowledge_point_names)
        for term in self._knowledge_terms(text):
            if any(term in name or name in term for name in mapped_names):
                if term not in knowledge_points:
                    knowledge_points.append(term)
            elif term not in sub_knowledge_points:
                sub_knowledge_points.append(term)

        def add_constraint(field: str, value: Any, clause_strength: str, reason: str = "") -> None:
            if clause_strength == "soft":
                strength = "soft"
                origin = "inferred"
                confidence = 0.7
            elif clause_strength == "default":
                strength = "default"
                origin = "system_default"
                confidence = 1.0
            else:
                # 教师直接陈述（无修饰词）与“只要/必须”都视为显式硬条件。
                strength = "hard"
                origin = "explicit"
                confidence = 1.0
            constraints.append(
                SearchConstraint(
                    field=field,
                    value=value,
                    strength=strength,
                    origin=origin,
                    confidence=confidence,
                    reason=reason,
                )
            )

        if grade:
            add_constraint("grade", grade, "explicit")
        if mapping.volume:
            add_constraint("volume", mapping.volume, "explicit")
        if mapping.knowledge_point_ids:
            term_strengths = [_strength_for_word(clauses, term) for term in knowledge_points]
            kp_strength = "hard" if any(s in ("hard", "explicit") for s in term_strengths) else "soft"
            add_constraint("knowledge_points", mapping.knowledge_point_ids, kp_strength)
        for term in sub_knowledge_points:
            add_constraint("knowledge_points", term, _strength_for_word(clauses, term))
        if mapping.chapter:
            add_constraint("chapter", mapping.chapter, "explicit")
        if difficulty is not None:
            add_constraint("difficulty", difficulty, _strength_for_word(clauses, difficulty_word))
        elif difficulty_range:
            add_constraint("difficulty_range", difficulty_range, _strength_for_word(clauses, difficulty_word))
        if question_types:
            type_word = next((word for word, _mapped in _QUESTION_TYPES if word in text), "题型")
            add_constraint("question_types", question_types, _strength_for_word(clauses, type_word))
        if regions:
            region_word = next((word for word, _mapped in _REGIONS if word in text), "地区")
            add_constraint("regions", regions, _strength_for_word(clauses, region_word))
        if year_from is not None:
            year_word = str(year_from)
            add_constraint("year", [year_from, year_to or year_from], _strength_for_word(clauses, year_word))
        if usage:
            # 教学用途是排序偏好，不是硬过滤条件。
            add_constraint("teaching_usage", usage, "soft")
        if exclude_ids:
            add_constraint("exclude_question_ids", exclude_ids, "hard")
        if exclude_similar:
            add_constraint("exclude_similar_to", exclude_similar, "hard")
        if require_verified:
            add_constraint("require_verified", True, "hard")

        return SearchIntent(
            raw_query=raw_query,
            grade=grade,
            volume=volume,
            curriculum=mapping,
            knowledge_points=knowledge_points,
            sub_knowledge_points=sub_knowledge_points,
            question_types=question_types,
            difficulty=difficulty,
            difficulty_range=difficulty_range,
            requested_count=requested_count,
            count=count,
            limit_applied=limit_applied,
            year_from=year_from,
            year_to=year_to,
            regions=regions,
            teaching_usage=usage or "general",
            exclude_question_ids=exclude_ids,
            exclude_similar_to=exclude_similar,
            require_verified=require_verified,
            allow_related_fallback=allow_related,
            constraints=constraints,
            parse_warnings=warnings,
        )

    # -- 教材映射 ---------------------------------------------------------

    def _map_curriculum(self, text: str, clauses: list[str]) -> CurriculumMapping:
        mapping = CurriculumMapping(version="CN-HS-MATH-2017-2020", textbook="PEP-A")
        if self._catalog is None:
            return mapping
        matched_node_ids: list[str] = []
        for term in self._curriculum_candidates(text):
            try:
                # 优先知识节点；只有没有 kp 命中时才退回章/节，避免章节点抢占 kp。
                matches = self._catalog.search(term, node_types={"knowledge_point"}, limit=3)
                if not matches:
                    matches = self._catalog.search(term, node_types={"section", "chapter"}, limit=1)
            except Exception:
                matches = []
            if not matches:
                continue
            best = matches[0]
            if best.node_id in matched_node_ids:
                continue
            matched_node_ids.append(best.node_id)
            node = self._catalog.get_node(best.node_id)
            path = self._catalog.path_for(best.node_id)
            mapping.volume = mapping.volume or path.get("volume")
            mapping.chapter = mapping.chapter or path.get("chapter")
            mapping.section = mapping.section or path.get("section")
            mapping.matched_nodes.append(
                CurriculumNodeRef(
                    node_id=best.node_id, code=best.code, name=best.name, node_type=best.node_type
                )
            )
            if best.node_type == "knowledge_point":
                mapping.knowledge_point_ids.append(best.node_id)
                mapping.knowledge_point_names.append(best.name)
        return mapping

    def _curriculum_candidates(self, text: str) -> list[str]:
        terms: list[str] = []
        for term in _COMMON_CHAPTER_TERMS:
            if term in text:
                terms.append(term)
        # 2-4 字片段：只保留真实出现在 catalog 索引中的候选，避免乱匹配。
        for clause in _split_clauses(text):
            for size in (4, 3, 2):
                for start in range(max(0, len(clause) - size + 1)):
                    chunk = clause[start : start + size]
                    if re.search(r"[\d道题个多少找给一些最好只要]", chunk):
                        continue
                    if chunk in terms:
                        continue
                    if chunk in self._term_index and chunk not in terms:
                        terms.append(chunk)
        return terms

    def _knowledge_terms(self, text: str) -> list[str]:
        terms: list[str] = []
        for term in _COMMON_CHAPTER_TERMS:
            if term in text and term not in terms:
                terms.append(term)
        for term in _SUB_KNOWLEDGE_TERMS:
            if term in text and term not in terms:
                terms.append(term)
        # 子知识点：catalog 名称中出现的特色词。
        for name in self._term_index:
            if len(name) >= 2 and name in text and name not in terms:
                terms.append(name)
        return terms
