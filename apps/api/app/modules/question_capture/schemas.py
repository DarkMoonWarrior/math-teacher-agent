from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


QuestionMediaSource = Literal["upload", "clipboard", "camera"]
QuestionMediaOperation = Literal["original", "rotate", "crop"]
QuestionRecognitionMode = Literal["local", "external"]


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


class QuestionRecognitionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: QuestionRecognitionMode
    external_processing_consent: bool = False


class QuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=12)
    text: str = Field(min_length=1, max_length=4000)


class LowConfidenceRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=1000)
    reason: str = Field(min_length=1, max_length=500)
    confidence: float | None = Field(default=None, ge=0, le=1)
    box: tuple[float, float, float, float] | None = None


class QuestionRecognitionReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stem_plain: str = Field(min_length=1, max_length=20000)
    stem_latex: str = Field(default="", max_length=20000)
    options: list[QuestionOption] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=2000)
    confirm: bool = False


class QuestionSolveReference(BaseModel):
    """Opaque, revision-pinned reference carried by browser and Agent."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, max_length=160)
    media_revision: int = Field(ge=1)
    recognition_revision: int = Field(ge=1)
    visual_processing_consent: bool = False


@dataclass(frozen=True, slots=True)
class PreparedQuestionInput:
    """Owner-resolved Solve input; storage paths never cross this seam."""

    question_text: str
    asset_id: str
    media_revision: int
    recognition_revision: int
    requires_visual_reasoning: bool
    visual_processing_consent: bool
    image_bytes: bytes | None
    image_mime_type: str | None


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
    recognition_status: Literal["not_started", "draft", "confirmed", "stale"] = "not_started"
    recognition_revision: int | None = None
    recognition_source_revision: int | None = None
    recognition_mode: QuestionRecognitionMode | None = None
    recognition_provider: str | None = None
    recognition_model: str | None = None
    stem_plain: str = ""
    stem_latex: str = ""
    options: list[QuestionOption] = Field(default_factory=list)
    requires_visual_reasoning: bool | None = None
    visual_observations: list[str] = Field(default_factory=list)
    low_confidence_regions: list[LowConfidenceRegion] = Field(default_factory=list)
    recognition_warnings: list[str] = Field(default_factory=list)
    external_processing_consent: bool = False
    teacher_review_note: str = ""
    visibility: Literal["private"] = "private"
