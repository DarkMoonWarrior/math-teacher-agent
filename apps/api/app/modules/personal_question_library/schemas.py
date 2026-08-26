from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.question_authoring import (
    GeneratedQuestionDraft,
    QuestionDraftEditableContent,
)


PersonalQuestionTag = Annotated[str, Field(min_length=1, max_length=40)]


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


class PersonalAuthoringSolutionRegenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class PersonalQuestionRevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    expected_updated_at: str = Field(min_length=1, max_length=80)
    content: QuestionDraftEditableContent
    edit_summary: str = Field(default="教师编辑已保存私题", min_length=1, max_length=500)


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


class PersonalQuestionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_updated_at: str = Field(min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    collection_id: str | None = Field(default=None, min_length=1, max_length=160)
    category_id: str | None = Field(default=None, min_length=1, max_length=160)
    tags: list[PersonalQuestionTag] | None = Field(default=None, max_length=20)
    sort_order: int | None = Field(default=None, ge=0, le=100_000)

    @model_validator(mode="after")
    def validate_update(self) -> "PersonalQuestionUpdate":
        fields = (self.name, self.collection_id, self.category_id, self.tags, self.sort_order)
        if all(value is None for value in fields):
            raise ValueError("至少提供一个需要修改的字段")
        if (self.collection_id is None) != (self.category_id is None):
            raise ValueError("移动私题时必须同时提供个人题库和分类")
        return self


class PersonalQuestionCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str = Field(min_length=1, max_length=160)
    category_id: str = Field(min_length=1, max_length=160)
    name: str | None = Field(default=None, min_length=1, max_length=120)


class PersonalQuestionVersionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_updated_at: str = Field(min_length=1, max_length=80)


class PersonalQuestionPermanentDelete(PersonalQuestionVersionCommand):
    confirmation: Literal["永久删除我的私题"]


class SavedPersonalQuestionDraft(GeneratedQuestionDraft):
    saved: Literal[True] = True


class PersonalQuestionView(OwnerOnlyContentPolicy):
    question_id: str
    collection_id: str
    category_id: str
    name: str
    source_draft_id: str
    selected_revision: int = Field(ge=1)
    tags: list[PersonalQuestionTag] = Field(default_factory=list, max_length=20)
    sort_order: int = Field(default=0, ge=0)
    lifecycle_state: Literal["active", "trashed"] = "active"
    trashed_at: str | None = None
    copied_from_question_id: str | None = None
    question: SavedPersonalQuestionDraft
    created_at: str
    updated_at: str


class PersonalQuestionList(BaseModel):
    query: str = ""
    lifecycle_state: Literal["active", "trashed"]
    items: list[PersonalQuestionView]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class PersonalQuestionExportArtifact(BaseModel):
    filename: str
    media_type: Literal["application/json", "text/markdown"]
    content: str


class PersonalQuestionDeletionReceipt(BaseModel):
    question_id: str
    source_draft_id: str
    active_storage_deleted: Literal[True] = True
    deleted_at: str
