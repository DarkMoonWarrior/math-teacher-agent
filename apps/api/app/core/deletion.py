from pathlib import Path
import stat
from collections.abc import Callable
from typing import Literal, TypeVar

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings, get_settings
from app.modules.data_lifecycle import DeletionObjectKind, OwnerDeletionLedger


ResultT = TypeVar("ResultT")


class OwnerPermanentDeleteCommand(BaseModel):
    """Fresh owner intent for deleting one selected private object."""

    model_config = ConfigDict(extra="forbid")
    expected_updated_at: str = Field(min_length=1, max_length=80)
    confirmation: Literal["永久删除我选择的内容"]


class OwnerPermanentDeleteResult(BaseModel):
    object_id: str
    object_kind: Literal["library_item", "question_capture", "exam_paper", "lesson_plan"]
    active_storage_deleted: Literal[True] = True
    independent_snapshots_preserved: Literal[True] = True


def get_owner_deletion_ledger(
    settings: Settings = Depends(get_settings),
) -> OwnerDeletionLedger:
    return OwnerDeletionLedger(settings.owner_deletion_ledger_db)


def execute_owner_permanent_delete(
    *,
    ledger: OwnerDeletionLedger,
    object_kind: DeletionObjectKind,
    object_id: str,
    owner_id: str,
    operation: Callable[[], ResultT],
) -> ResultT:
    """Keep a durable restore tombstone across a successful destructive operation."""

    tombstone = ledger.record(
        object_kind=object_kind,
        object_id=object_id,
        owner_id=owner_id,
    )
    try:
        return operation()
    except BaseException:
        # The business store transaction rolls back first. Best-effort removal is
        # conditional on this exact intent so it cannot erase a newer tombstone.
        try:
            ledger.remove(tombstone)
        except Exception:
            pass
        raise


def is_link_or_reparse(path: Path) -> bool:
    """Reject symbolic links and Windows reparse points before destructive IO."""

    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )
