from __future__ import annotations

import re

from app.modules.exam_papers.schemas import (
    PaperBlueprintBrief,
    PaperBlueprintDraft,
    PaperBlueprintSection,
)
from app.modules.teacher_memory import TeacherPlanningDefaults, TeacherPlanningPreference


class PaperBlueprintPlanningError(ValueError):
    pass


class PaperBlueprintPlanning:
    """Turns a teacher's brief into an editable paper blueprint without side effects."""

    KNOWLEDGE_POINTS = (
        "集合",
        "复数",
        "函数",
        "导数",
        "三角函数",
        "平面向量",
        "数列",
        "不等式",
        "立体几何",
        "空间向量",
        "直线与圆",
        "圆锥曲线",
        "解析几何",
        "计数原理",
        "概率",
        "统计",
    )
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

    def plan(
        self,
        command: PaperBlueprintBrief,
        *,
        defaults: TeacherPlanningDefaults | None = None,
    ) -> PaperBlueprintDraft:
        brief = " ".join(command.brief.strip().split())
        self._ensure_high_school_scope(brief)
        assumptions: list[str] = []
        applied_preferences: list[TeacherPlanningPreference] = []
        planning_defaults = defaults or TeacherPlanningDefaults()
        grade = self._grade(brief, assumptions, applied_preferences, planning_defaults)
        usage = self._usage(brief, assumptions)
        duration = self._duration(brief, usage, assumptions)
        target_score = self._target_score(brief, duration, assumptions)
        difficulty = self._difficulty(
            brief,
            assumptions,
            applied_preferences,
            planning_defaults,
        )
        knowledge_points = self._knowledge_points(brief, assumptions)
        sections = self._sections(brief, duration, target_score)
        title = self._title(brief, grade, usage, knowledge_points)
        return PaperBlueprintDraft(
            source_brief=brief,
            title=title,
            grade_scope=grade,
            teaching_usage=usage,
            duration_minutes=duration,
            target_score=target_score,
            difficulty_profile=difficulty,
            knowledge_points=knowledge_points,
            sections=sections,
            applied_preferences=applied_preferences,
            assumptions=assumptions,
        )

    def _ensure_high_school_scope(self, brief: str) -> None:
        marker = next((item for item in self.UNIVERSITY_MARKERS if item in brief), None)
        if marker:
            raise PaperBlueprintPlanningError(
                f"M9 只支持中国普通高中数学组卷；“{marker}”超出当前课程边界。"
            )
        if "大学" in brief or "本科" in brief:
            raise PaperBlueprintPlanningError("M9 只支持中国普通高中数学组卷。")

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
    def _usage(brief: str, assumptions: list[str]) -> str:
        for marker, label in (
            ("期中", "期中检测"),
            ("期末", "期末检测"),
            ("月考", "月度检测"),
            ("专题", "专题测验"),
            ("单元", "单元测验"),
            ("随堂", "随堂练习"),
            ("模拟", "模拟考试"),
        ):
            if marker in brief:
                return label
        assumptions.append("未明确用途，暂按阶段检测规划。")
        return "阶段检测"

    @staticmethod
    def _duration(brief: str, usage: str, assumptions: list[str]) -> int:
        match = re.search(r"(?<!\d)(\d{2,3})\s*分钟", brief)
        if match:
            value = int(match.group(1))
            if 10 <= value <= 300:
                return value
        default = 20 if usage == "随堂练习" else 60 if "专题" in usage else 90
        assumptions.append(f"未明确有效考试时间，暂按 {default} 分钟规划。")
        return default

    @staticmethod
    def _target_score(brief: str, duration: int, assumptions: list[str]) -> float:
        patterns = (
            r"(?:总分|满分|目标分值)\s*(?:为|是|[:：])?\s*(\d{1,3}(?:\.5)?)\s*分",
            r"(\d{2,3}(?:\.5)?)\s*分制",
        )
        for pattern in patterns:
            match = re.search(pattern, brief)
            if match:
                value = float(match.group(1))
                if 5 <= value <= 300:
                    return value
        default = 40.0 if duration <= 30 else 100.0 if duration <= 90 else 150.0
        assumptions.append(f"未明确总分，暂按 {default:g} 分规划。")
        return default

    @staticmethod
    def _difficulty(
        brief: str,
        assumptions: list[str],
        applied_preferences: list[TeacherPlanningPreference],
        defaults: TeacherPlanningDefaults,
    ) -> str:
        if any(marker in brief for marker in ("压轴", "偏难", "高难", "提升", "挑战")):
            return "challenge"
        if any(marker in brief for marker in ("基础", "巩固", "入门")):
            return "foundation"
        if any(marker in brief for marker in ("中等", "均衡", "常规")):
            return "balanced"
        preference = defaults.get("default_difficulty")
        if (
            preference
            and isinstance(preference.value, int)
            and not isinstance(preference.value, bool)
            and 1 <= preference.value <= 5
        ):
            profile = (
                "foundation"
                if preference.value <= 2
                else "balanced"
                if preference.value == 3
                else "challenge"
            )
            profile_label = {
                "foundation": "基础梯度",
                "balanced": "均衡梯度",
                "challenge": "挑战梯度",
            }[profile]
            applied_preferences.append(preference)
            assumptions.append(
                f"未明确难度结构，已使用教师偏好“{preference.value}/5（{profile_label}）”；本次可直接修改覆盖。"
            )
            return profile
        assumptions.append("未明确难度结构，暂按均衡梯度规划。")
        return "balanced"

    def _knowledge_points(self, brief: str, assumptions: list[str]) -> list[str]:
        points = [
            item
            for item in self.KNOWLEDGE_POINTS
            if item != "函数" and item in brief
        ]
        if "函数" in brief.replace("三角函数", ""):
            points.insert(0, "函数")
        if "椭圆" in brief or "双曲线" in brief or "抛物线" in brief:
            points.append("圆锥曲线")
        if "直线" in brief and "直线与圆" not in points:
            points.append("直线与圆")
        points = list(dict.fromkeys(points))
        if points:
            return points
        assumptions.append("未识别出明确知识范围，暂按高中数学综合范围规划。")
        return ["高中数学综合"]

    @staticmethod
    def _sections(brief: str, duration: int, target_score: float) -> list[PaperBlueprintSection]:
        total_count = 6 if duration <= 30 else 10 if duration <= 60 else 15 if duration <= 90 else 19
        counts = {
            "single_choice": max(2, round(total_count * 0.42)),
            "multiple_choice": max(1, round(total_count * 0.16)),
            "fill_blank": max(1, round(total_count * 0.16)),
        }
        counts["open_response"] = max(1, total_count - sum(counts.values()))
        explicit_open = re.search(r"(?:含|包含|安排)?\s*(\d{1,2})\s*道\s*(?:解答题|大题)", brief)
        if explicit_open:
            requested = max(1, min(int(explicit_open.group(1)), total_count - 3))
            delta = requested - counts["open_response"]
            counts["open_response"] = requested
            counts["single_choice"] = max(1, counts["single_choice"] - delta)
        raw_scores = [target_score * 0.27, target_score * 0.12, target_score * 0.1]
        scores = [round(value * 2) / 2 for value in raw_scores]
        scores.append(round((target_score - sum(scores)) * 2) / 2)
        difference = target_score - sum(scores)
        scores[-1] += difference
        definitions = (
            ("single-choice", "单项选择题", "single_choice"),
            ("multiple-choice", "多项选择题", "multiple_choice"),
            ("fill-blank", "填空题", "fill_blank"),
            ("open-response", "解答题", "open_response"),
        )
        return [
            PaperBlueprintSection(
                section_id=section_id,
                title=title,
                question_type=question_type,
                question_count=counts[question_type],
                target_score=score,
            )
            for (section_id, title, question_type), score in zip(definitions, scores, strict=True)
        ]

    @staticmethod
    def _title(brief: str, grade: str, usage: str, knowledge_points: list[str]) -> str:
        quoted = re.search(r"[《“](.{2,80}?)[》”]", brief)
        if quoted:
            return quoted.group(1).strip()
        focus = "、".join(knowledge_points[:3])
        return f"{grade}{focus}{usage}"
