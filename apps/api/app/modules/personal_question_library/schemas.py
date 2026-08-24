from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.question_authoring import (
    GeneratedQuestionDraft,
    QuestionDraftEditableContent,
)


class PersonalCollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)


class PersonalCollectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def require_change(self) -> "PersonalCollectionUpdate":
        if self.name is None and self.description is None:
            raise ValueError("至少提供一个需要修改的字段")
        return self


class PersonalCategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    sort_order: int = Field(default=0, ge=0, le=10_000)


class PersonalCategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    sort_order: int | None = Field(default=None, ge=0, le=10_000)

    @model_validator(mode="after")
    def require_change(self) -> "PersonalCategoryUpdate":
        if self.name is None and self.description is None and self.sort_order is None:
            raise ValueError("至少提供一个需要修改的字段")
        return self


class OwnerOnlyContentPolicy(BaseModel):
    visibility: Literal["owner_only"] = "owner_only"
    public_search_allowed: Literal[False] = False
    share_allowed: Literal[False] = False
    commercial_use_allowed: Literal[False] = False
    model_training_allowed: Literal[False] = False


class PersonalCollectionView(OwnerOnlyContentPolicy):
    collection_id: str
    name: str
    description: str
    category_count: int = Field(ge=0)
    question_count: int = Field(default=0, ge=0)
    created_at: str
    updated_at: str


class PersonalCollectionList(BaseModel):
    items: list[PersonalCollectionView]
    total: int = Field(ge=0)


class PersonalCategoryView(OwnerOnlyContentPolicy):
    category_id: str
    collection_id: str
    name: str
    description: str
    sort_order: int = Field(ge=0)
    question_count: int = Field(default=0, ge=0)
    created_at: str
    updated_at: str


class PersonalCategoryList(BaseModel):
    collection_id: str
    items: list[PersonalCategoryView]
    total: int = Field(ge=0)


class PersonalAuthoringRevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    content: QuestionDraftEditableContent
    edit_summary: str = Field(default="教师编辑", min_length=1, max_length=500)


class PersonalAuthoringRevisionView(BaseModel):
    draft_id: str
    revision_number: int = Field(ge=1)
    revision_source: Literal["ai_generated", "teacher_edit"]
    edit_summary: str
    draft: GeneratedQuestionDraft
    created_at: str


class PersonalAuthoringRevisionList(BaseModel):
    draft_id: str
    current_revision: int = Field(ge=1)
    items: list[PersonalAuthoringRevisionView]
    total: int = Field(ge=1)


class PersonalAuthoringDraftView(OwnerOnlyContentPolicy):
    draft_id: str
    current_revision: int = Field(ge=1)
    saved: bool
    saved_question_id: str | None = None
    current: PersonalAuthoringRevisionView
    created_at: str
    updated_at: str


class PersonalQuestionSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    collection_id: str = Field(min_length=1, max_length=160)
    category_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=120)


class SavedPersonalQuestionDraft(GeneratedQuestionDraft):
    saved: Literal[True] = True


class PersonalQuestionView(OwnerOnlyContentPolicy):
    question_id: str
    collection_id: str
    category_id: str
    name: str
    source_draft_id: str
    selected_revision: int = Field(ge=1)
    question: SavedPersonalQuestionDraft
    created_at: str
    updated_at: str
