from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


PRIVATE_OBJECT_BINDING_SCHEMA_VERSION = "m14.private-object-binding.v1"


class PrivateObjectAccessDenied(PermissionError):
    """A private object binding did not belong to the supplied owner scope."""


class PrivateObjectBindingError(ValueError):
    """A private object binding request was structurally invalid."""


class PrivateObjectDomain(StrEnum):
    PRIVATE_LIBRARY_SOURCE = "private-library-source"
    QUESTION_CAPTURE_REVISION = "question-capture-revision"
    PDF_IMPORT_SOURCE = "pdf-import-source"
    PDF_IMPORT_CROP = "pdf-import-crop"
    PAPER_VERSION_ASSET = "paper-version-asset"
    LESSON_VERSION_ASSET = "lesson-version-asset"
    EPHEMERAL_EXPORT = "ephemeral-export"
    BACKGROUND_JOB_RESULT = "background-job-result"


class PrivateObjectRetention(StrEnum):
    OWNER_LIFECYCLE = "owner-lifecycle"
    RESPONSE_COMPLETE = "response-complete"
    TERMINAL_24H = "terminal-24h"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateObjectScope:
    tenant_id: str
    owner_id: str

    def __repr__(self) -> str:
        return "PrivateObjectScope(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateObjectBinding:
    storage_key: str
    domain: PrivateObjectDomain
    retention: PrivateObjectRetention
    schema_version: str = PRIVATE_OBJECT_BINDING_SCHEMA_VERSION

    def __repr__(self) -> str:
        return (
            "PrivateObjectBinding("
            f"domain={self.domain!r}, retention={self.retention!r}, "
            f"schema_version={self.schema_version!r}, storage_key=<redacted>)"
        )
