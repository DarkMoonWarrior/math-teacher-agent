from __future__ import annotations

from pathlib import Path

from app.core.deletion import is_link_or_reparse


def remove_ephemeral_export(path: Path, *, output_root: Path) -> None:
    """Remove one rendered download after its response has finished streaming."""

    root = output_root.resolve()
    if is_link_or_reparse(path):
        return
    candidate = path.resolve()
    if root not in candidate.parents or not candidate.is_file():
        return
    candidate.unlink(missing_ok=True)
