from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


QuestionMediaSource = Literal["upload", "clipboard", "camera"]
QuestionMediaOperation = Literal["original", "rotate", "crop"]


class QuestionCaptureCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_id: str = Field(min_length=1, max_length=120)
    source: QuestionMediaSource
    private_storage_acknowledged: bool


class QuestionMediaCrop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class QuestionMediaTransformCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["rotate", "crop"]
    degrees: Literal[90, 180, 270] | None = None
    crop: QuestionMediaCrop | None = None


class QuestionMediaRevision(BaseModel):
    revision: int = Field(ge=1)
    source_revision: int | None
    operation: QuestionMediaOperation
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    content_endpoint: str
    created_at: str


class QuestionMediaAsset(BaseModel):
    asset_id: str
    original_filename: str
    source: QuestionMediaSource
    source_sha256: str
    current_revision: int = Field(ge=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    size_bytes: int = Field(gt=0)
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    clarity_status: Literal["clear", "review_needed"]
    warnings: list[str] = Field(default_factory=list)
    revisions: list[QuestionMediaRevision]
    visibility: Literal["private"] = "private"
    public_search_allowed: Literal[False] = False
    model_training_allowed: Literal[False] = False
    created_at: str
    updated_at: str


class QuestionInputBundle(BaseModel):
    asset: QuestionMediaAsset
    recognition_status: Literal["not_started"] = "not_started"
    stem_plain: str = ""
    stem_latex: str = ""
    options: list[dict[str, str]] = Field(default_factory=list)
    requires_visual_reasoning: bool | None = None
    low_confidence_regions: list[dict[str, object]] = Field(default_factory=list)
    recognition_warnings: list[str] = Field(default_factory=list)
    external_processing_consent: Literal[False] = False
    visibility: Literal["private"] = "private"
