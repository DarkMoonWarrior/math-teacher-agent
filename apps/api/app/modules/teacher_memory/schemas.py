from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TeacherPreferenceKey = Literal[
    "default_grade",
    "default_difficulty",
    "default_lesson_minutes",
    "solution_detail_level",
    "preferred_question_types",
]
TeacherPreferenceValue = str | int | list[str]


class TeacherPreferenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["teacher_explicit"] = "teacher_explicit"
    label: str = "教师明确设置"
    confidence: float = Field(default=1.0, ge=0, le=1)


class TeacherPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: TeacherPreferenceKey
    label: str
    value: TeacherPreferenceValue
    source: TeacherPreferenceSource
    updated_at: str


class TeacherPlanningPreference(BaseModel):
    """One provenance-preserving preference that a planner may use as a default."""

    model_config = ConfigDict(extra="forbid")

    key: TeacherPreferenceKey
    label: str
    value: TeacherPreferenceValue
    source: TeacherPreferenceSource


class TeacherPlanningDefaults(BaseModel):
    """Allowlisted defaults exposed to planning modules without owner identity."""

    model_config = ConfigDict(extra="forbid")

    preferences: list[TeacherPlanningPreference] = Field(default_factory=list)

    def get(self, key: TeacherPreferenceKey) -> TeacherPlanningPreference | None:
        return next((item for item in self.preferences if item.key == key), None)


class TeacherMemoryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)
    auto_learning_enabled: bool = False
    preferences: list[TeacherPreference] = Field(default_factory=list)
    privacy_note: str = "仅保存结构化教学偏好，不保存题目、解析、教案或私人资料正文。"


class TeacherMemoryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["upsert", "remove", "set_auto_learning"]
    key: TeacherPreferenceKey | None = None
    value: TeacherPreferenceValue | None = None
    enabled: bool | None = None
    expected_version: int | None = Field(default=None, ge=0)
