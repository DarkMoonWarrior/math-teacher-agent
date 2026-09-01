from __future__ import annotations

import math
import re

from app.modules.curriculum import InMemoryCurriculumCatalog
from app.modules.lesson_plans.schemas import (
    LessonBlueprintBrief,
    LessonBlueprintCurriculumCandidate,
    LessonBlueprintDraft,
    LessonBlueprintPhase,
    LessonType,
)
from app.modules.teacher_memory import TeacherPlanningDefaults, TeacherPlanningPreference


class LessonBlueprintPlanningError(ValueError):
    pass


class LessonBlueprintPlanning:
    """Turns one teacher brief into an editable lesson blueprint without side effects."""

    UNIVERSITY_MARKERS = (
        "高等数学",
        "线性代数",
        "数学分析",
        "实变函数",
        "复变函数",
        "抽象代数",
        "泛函分析",
        "随机过程",
        "马尔可夫链",
        "傅里叶分析",
        "偏微分方程",
    )
    TOPIC_MARKERS = (
        "函数单调性",
        "函数奇偶性",
        "函数零点",
        "基本不等式",
        "三角恒等变换",
        "三角函数",
        "平面向量",
        "空间向量",
        "立体几何",
        "直线与圆",
        "圆锥曲线",
        "排列组合",
        "计数原理",
        "等差数列",
        "等比数列",
        "概率",
        "统计",
        "集合",
        "复数",
        "导数",
        "椭圆",
        "双曲线",
        "抛物线",
        "数列",
        "函数",
    )
    REQUIRED_BLOCKS = [
        "objectives",
        "key_points",
        "difficulties",
        "teaching_flow",
        "homework",
        "board_plan",
        "teacher_notes",
    ]

    def __init__(
        self,
        *,
        curriculum_catalog: InMemoryCurriculumCatalog,
    ) -> None:
        self.curriculum_catalog = curriculum_catalog

    def plan(
        self,
        command: LessonBlueprintBrief,
        *,
        defaults: TeacherPlanningDefaults | None = None,
    ) -> LessonBlueprintDraft:
        brief = " ".join(command.brief.strip().split())
        self._ensure_high_school_scope(brief)
        assumptions: list[str] = []
        applied_preferences: list[TeacherPlanningPreference] = []
        planning_defaults = defaults or TeacherPlanningDefaults()
        grade = self._grade(brief, assumptions, applied_preferences, planning_defaults)
        lesson_type, lesson_format = self._lesson_type(brief, assumptions)
        duration = self._duration(
            brief,
            assumptions,
            applied_preferences,
            planning_defaults,
        )
        student_profile = self._student_profile(brief, assumptions)
        topic_query = self._topic_query(brief)
        candidates = self._curriculum_candidates(topic_query)
        selected = candidates[0] if candidates else None
        if selected is None:
            assumptions.append(
                "未匹配到明确的人教 A 版教材节点；生成正文前必须由教师选择教材节点。"
            )
        elif len(candidates) > 1:
            assumptions.append(
                f"已暂选“{selected.name}”作为教材节点；生成正文前可改选其他候选。"
            )
        focus = self._focus(brief, selected.name if selected else topic_query)
        question_count = self._question_count(brief, assumptions)
        objectives, key_points, difficulties = self._learning_requirements(
            selected,
            topic_query,
        )
        phases = self._phases(duration, lesson_type, lesson_format)
        return LessonBlueprintDraft(
            source_brief=brief,
            title=f"{grade}{selected.name if selected else topic_query}{lesson_format}教案",
            grade_scope=grade,
            lesson_type=lesson_type,
            lesson_format=lesson_format,
            duration_minutes=duration,
            student_profile=student_profile,
            focus=focus,
            question_count=question_count,
            curriculum_query=topic_query,
            selected_curriculum_node_id=selected.node_id if selected else None,
            curriculum_candidates=candidates,
            objectives=objectives,
            key_points=key_points,
            difficulties=difficulties,
            phases=phases,
            required_blocks=self.REQUIRED_BLOCKS,
            applied_preferences=applied_preferences,
            assumptions=assumptions,
        )

    def _ensure_high_school_scope(self, brief: str) -> None:
        marker = next((item for item in self.UNIVERSITY_MARKERS if item in brief), None)
        if marker:
            raise LessonBlueprintPlanningError(
                f"M10 只支持中国普通高中数学教案；“{marker}”超出当前课程边界。"
            )
        if "大学" in brief or "本科" in brief:
            raise LessonBlueprintPlanningError("M10 只支持中国普通高中数学教案。")

    @staticmethod
    def _grade(
        brief: str,
        assumptions: list[str],
        applied_preferences: list[TeacherPlanningPreference],
        defaults: TeacherPlanningDefaults,
    ) -> str:
        match = re.search(r"高[一二三123]", brief)
        if match:
            return match.group(0).translate(str.maketrans("123", "一二三"))
        preference = defaults.get("default_grade")
        if (
            preference
            and isinstance(preference.value, str)
            and preference.value in {"高一", "高二", "高三", "高中通用"}
        ):
            applied_preferences.append(preference)
            assumptions.append(
                f"未明确年级，已使用教师偏好“{preference.value}”；本次可直接修改覆盖。"
            )
            return preference.value
        assumptions.append("未明确年级，暂按高中通用范围规划。")
        return "高中通用"

    @staticmethod
    def _lesson_type(
        brief: str,
        assumptions: list[str],
    ) -> tuple[LessonType, str]:
        if "讲评" in brief:
            return "exercise", "试卷讲评课"
        if "习题" in brief or "练习课" in brief:
            return "exercise", "习题课"
        if "复习" in brief:
            return "review", "专题复习课"
        if "新授" in brief or "第一课时" in brief:
            return "new_lesson", "新授课"
        assumptions.append("未明确课型，暂按新授课规划。")
        return "new_lesson", "新授课"

    @staticmethod
    def _duration(
        brief: str,
        assumptions: list[str],
        applied_preferences: list[TeacherPlanningPreference],
        defaults: TeacherPlanningDefaults,
    ) -> int:
        match = re.search(r"(?<!\d)(\d{2,3})\s*分钟", brief)
        if match:
            value = int(match.group(1))
            if 20 <= value <= 120:
                return value
        preference = defaults.get("default_lesson_minutes")
        if (
            preference
            and isinstance(preference.value, int)
            and not isinstance(preference.value, bool)
            and 20 <= preference.value <= 120
        ):
            applied_preferences.append(preference)
            assumptions.append(
                f"未明确有效课时，已使用教师偏好“{preference.value} 分钟”；本次可直接修改覆盖。"
            )
            return preference.value
        assumptions.append("未明确有效课时，暂按 45 分钟规划。")
        return 45

    @staticmethod
    def _student_profile(brief: str, assumptions: list[str]) -> str:
        profiles = (
            ("基础薄弱", "基础较薄弱，需要降低起点并提供分步支架"),
            ("基础较弱", "基础较薄弱，需要降低起点并提供分步支架"),
            ("中等", "基础中等，能够完成教材基础练习，需要通过问题链促进概括"),
            ("基础较好", "基础较好，可增加方法比较、变式与迁移任务"),
            ("拔高", "基础较好，课堂侧重方法迁移、综合表达与高阶思维"),
        )
        for marker, profile in profiles:
            if marker in brief:
                return profile
        assumptions.append("未明确学情，暂按基础中等、需要适度支架规划。")
        return "基础中等，能够完成教材基础练习，抽象概括能力需要支架"

    def _topic_query(self, brief: str) -> str:
        normalized_brief = self._normalize(brief)
        names = sorted(
            {
                node.name
                for node in self.curriculum_catalog.list_nodes()
                if node.node_type in {"section", "knowledge_point"}
                and len(self._normalize(node.name)) >= 2
            },
            key=lambda value: len(self._normalize(value)),
            reverse=True,
        )
        direct = next(
            (
                name
                for name in names
                if self._normalize(name) in normalized_brief
            ),
            None,
        )
        if direct:
            return direct
        marker = next((item for item in self.TOPIC_MARKERS if item in brief), None)
        return marker or "高中数学综合"

    def _curriculum_candidates(
        self,
        query: str,
    ) -> list[LessonBlueprintCurriculumCandidate]:
        if query == "高中数学综合":
            return []
        matches = self.curriculum_catalog.search(
            query,
            node_types={"section", "knowledge_point"},
            limit=5,
        )
        candidates: list[LessonBlueprintCurriculumCandidate] = []
        for item in matches:
            node = self.curriculum_catalog.get_node(item.node_id)
            candidates.append(
                LessonBlueprintCurriculumCandidate(
                    node_id=node.node_id,
                    node_type=node.node_type,  # type: ignore[arg-type]
                    name=node.name,
                    volume=item.volume,
                    chapter=item.chapter,
                    section=item.section,
                    description=node.description,
                    competencies=node.primary_competencies,
                    common_errors=node.common_errors,
                    catalog_status=node.status,
                    reviewed_by=node.reviewed_by,
                    match_score=item.match_score,
                )
            )
        return candidates

    @staticmethod
    def _focus(brief: str, topic: str) -> str:
        match = re.search(
            r"(?:重点|侧重|突出)(?:是|为|放在|讲清)?[：:]?\s*([^，。；;]{2,100})",
            brief,
        )
        if match:
            return match.group(1).strip()
        return f"围绕{topic}建立概念、方法、表达与课堂评价的对应关系"

    @staticmethod
    def _question_count(brief: str, assumptions: list[str]) -> int:
        match = re.search(r"(?<!\d)(\d)\s*道\s*(?:例题|练习题|练习|题)", brief)
        if match:
            return min(8, int(match.group(1)))
        assumptions.append("未明确例题与练习数量，暂按 3 道受控题目规划。")
        return 3

    @staticmethod
    def _learning_requirements(
        candidate: LessonBlueprintCurriculumCandidate | None,
        topic: str,
    ) -> tuple[list[str], list[str], list[str]]:
        name = candidate.name if candidate else topic
        objectives = [
            f"理解并准确表达{name}的核心概念、条件与结论。",
            f"能在典型问题中运用{name}并说明关键依据。",
        ]
        if candidate and candidate.competencies:
            objectives.append(
                f"在问题探究与表达中发展{'、'.join(candidate.competencies[:3])}。"
            )
        key_points = [f"{name}的核心概念、表示与基本方法"]
        difficulties = (
            candidate.common_errors[:3]
            if candidate and candidate.common_errors
            else [f"在不同表征之间建立{name}的条件与结论联系"]
        )
        return objectives, key_points, difficulties

    def _phases(
        self,
        duration: int,
        lesson_type: LessonType,
        lesson_format: str,
    ) -> list[LessonBlueprintPhase]:
        definitions = {
            "new_lesson": (
                ("diagnosis", "情境与诊断", 0.12, "唤起先备知识并暴露真实起点"),
                ("question", "提出问题", 0.14, "形成贯穿课堂的核心问题"),
                ("construction", "概念与方法建构", 0.34, "经历观察、猜想、论证与表达"),
                ("practice", "例题与分层练习", 0.28, "通过受控题目完成理解、迁移与反馈"),
                ("summary", "总结与作业", 0.12, "回扣目标并布置可追踪作业"),
            ),
            "review": (
                ("diagnosis", "诊断与目标", 0.16, "用诊断任务定位知识与方法断点"),
                ("structure", "结构梳理", 0.24, "重建知识、方法与易错点网络"),
                ("example", "典型问题研讨", 0.28, "比较方法并提炼可迁移策略"),
                ("practice", "分层巩固", 0.22, "针对诊断结果完成分层练习"),
                ("summary", "评价与作业", 0.10, "形成课堂证据并安排后续巩固"),
            ),
            "exercise": (
                ("diagnosis", "问题归类", 0.14, f"围绕{lesson_format}确定共性问题"),
                ("analysis", "错因与方法分析", 0.26, "区分知识、方法、表达与审题问题"),
                ("example", "典型题讲评", 0.28, "展示完整推理并比较不同方法"),
                ("practice", "变式与订正", 0.22, "通过变式确认订正是否真正发生"),
                ("summary", "总结与作业", 0.10, "沉淀策略并安排针对性任务"),
            ),
        }[lesson_type]
        minutes = self._allocate_minutes(duration, [item[2] for item in definitions])
        return [
            LessonBlueprintPhase(
                phase_id=phase_id,
                title=title,
                minutes=minute,
                purpose=purpose,
            )
            for (phase_id, title, _, purpose), minute in zip(
                definitions,
                minutes,
                strict=True,
            )
        ]

    @staticmethod
    def _allocate_minutes(duration: int, weights: list[float]) -> list[int]:
        remaining = duration - len(weights)
        raw = [remaining * weight for weight in weights]
        allocated = [1 + math.floor(value) for value in raw]
        difference = duration - sum(allocated)
        order = sorted(
            range(len(weights)),
            key=lambda index: (raw[index] - math.floor(raw[index]), weights[index]),
            reverse=True,
        )
        for index in order[:difference]:
            allocated[index] += 1
        return allocated

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())
