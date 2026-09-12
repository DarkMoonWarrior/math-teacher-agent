from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


PRIVATE_OBJECT_BINDING_SCHEMA_VERSION = "m14.private-object-binding.v1"


class PrivateObjectAccessDenied(PermissionError):
    """A private object binding did not belong to the supplied owner scope."""


class PrivateObjectBindingError(ValueError):
    """A private object binding request was structurally invalid."""


class PrivateObjectStoreError(RuntimeError):
    """The private byte store could not complete a safe operation."""


class PrivateObjectConflict(PrivateObjectStoreError):
    """A deterministic object key already contains different bytes."""


class PrivateObjectNotFound(PrivateObjectStoreError):
    """The authorized private object does not exist."""


class PrivateObjectIntegrityError(PrivateObjectStoreError):
    """Persisted private object bytes do not match their envelope."""


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


class PrivateObjectPutOutcome(StrEnum):
    CREATED = "created"
    ALREADY_PRESENT = "already-present"


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


@dataclass(frozen=True, slots=True, repr=False)
class PrivateObjectReceipt:
    outcome: PrivateObjectPutOutcome
    byte_length: int
    checksum: str

    def __repr__(self) -> str:
        return (
            "PrivateObjectReceipt("
            f"outcome={self.outcome!r}, byte_length={self.byte_length}, "
            "checksum=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class PrivateObjectDeleteReceipt:
    deleted: bool
