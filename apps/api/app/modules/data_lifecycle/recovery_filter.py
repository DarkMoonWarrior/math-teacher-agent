from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from .ledger import DeletionTombstone


class RestoredOwnerDataFilter:
    """Apply current deletion tombstones to an isolated restored payload."""

    def apply(self, payload_root: Path, tombstones: tuple[DeletionTombstone, ...]) -> int:
        suppressed = 0
        by_kind: dict[str, list[DeletionTombstone]] = {}
        for item in tombstones:
            by_kind.setdefault(item.object_kind, []).append(item)
        suppressed += self._private_library(payload_root, by_kind.get("library_item", []))
        suppressed += self._captures(payload_root, by_kind.get("question_capture", []))
        suppressed += self._personal_questions(payload_root, by_kind.get("personal_question", []))
        suppressed += self._papers(payload_root, by_kind.get("exam_paper", []))
        suppressed += self._lessons(payload_root, by_kind.get("lesson_plan", []))
        return suppressed

    def _private_library(self, root: Path, items: list[DeletionTombstone]) -> int:
        database = root / "private_library" / "store.sqlite3"
        if not items or not database.is_file():
            return 0
        removed = 0
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.row_factory = sqlite3.Row
            for item in items:
                row = connection.execute(
                    "SELECT stored_name FROM library_items WHERE library_item_id = ? AND owner_id = ?",
                    (item.object_id, item.owner_id),
                ).fetchone()
                if row is None:
                    continue
                for table in ("library_question_candidates", "library_ocr_runs", "library_text_revisions", "library_lifecycle_events"):
                    connection.execute(f"DELETE FROM {table} WHERE library_item_id = ?", (item.object_id,))
                connection.execute("DELETE FROM library_items WHERE library_item_id = ? AND owner_id = ?", (item.object_id, item.owner_id))
                self._unlink(root / "private_library_files", row["stored_name"])
                removed += 1
        return removed

    def _captures(self, root: Path, items: list[DeletionTombstone]) -> int:
        database = root / "question_capture" / "store.sqlite3"
        if not items or not database.is_file():
            return 0
        removed = 0
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.row_factory = sqlite3.Row
            for item in items:
                exists = connection.execute(
                    "SELECT 1 FROM question_capture_assets WHERE asset_id = ? AND owner_id = ?",
                    (item.object_id, item.owner_id),
                ).fetchone()
                if exists is None:
                    continue
                media = connection.execute("SELECT stored_name FROM question_capture_revisions WHERE asset_id = ?", (item.object_id,)).fetchall()
                for table in ("question_capture_solve_uses", "question_capture_recognitions", "question_capture_revisions"):
                    connection.execute(f"DELETE FROM {table} WHERE asset_id = ?", (item.object_id,))
                connection.execute("DELETE FROM question_capture_assets WHERE asset_id = ? AND owner_id = ?", (item.object_id, item.owner_id))
                for row in media:
                    self._unlink(root / "question_capture_files", row["stored_name"])
                removed += 1
        return removed

    def _personal_questions(self, root: Path, items: list[DeletionTombstone]) -> int:
        database = root / "personal_question_library" / "store.sqlite3"
        if not items or not database.is_file():
            return 0
        removed = 0
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.row_factory = sqlite3.Row
            for item in items:
                row = connection.execute(
                    "SELECT source_draft_id FROM personal_questions WHERE question_id = ? AND owner_id = ?",
                    (item.object_id, item.owner_id),
                ).fetchone()
                if row is None:
                    continue
                connection.execute("DELETE FROM personal_questions WHERE question_id = ? AND owner_id = ?", (item.object_id, item.owner_id))
                connection.execute("DELETE FROM personal_authoring_revisions WHERE draft_id = ? AND owner_id = ?", (row["source_draft_id"], item.owner_id))
                connection.execute("DELETE FROM personal_authoring_drafts WHERE draft_id = ? AND owner_id = ?", (row["source_draft_id"], item.owner_id))
                removed += 1
        return removed

    def _papers(self, root: Path, items: list[DeletionTombstone]) -> int:
        database = root / "exam_papers" / "store.sqlite3"
        if not items or not database.is_file():
            return 0
        removed = 0
        with closing(sqlite3.connect(database)) as connection, connection:
            for item in items:
                exists = connection.execute("SELECT 1 FROM exam_papers WHERE exam_paper_id = ? AND owner_id = ?", (item.object_id, item.owner_id)).fetchone()
                if exists is None:
                    continue
                connection.execute("DELETE FROM exam_paper_revisions WHERE exam_paper_id = ? AND owner_id = ?", (item.object_id, item.owner_id))
                connection.execute("DELETE FROM exam_papers WHERE exam_paper_id = ? AND owner_id = ?", (item.object_id, item.owner_id))
                self._remove_flat_directory(root / "exam_paper_assets" / item.object_id, root / "exam_paper_assets")
                removed += 1
        return removed

    def _lessons(self, root: Path, items: list[DeletionTombstone]) -> int:
        database = root / "lesson_plans" / "store.sqlite3"
        if not items or not database.is_file():
            return 0
        removed = 0
        with closing(sqlite3.connect(database)) as connection, connection:
            for item in items:
                exists = connection.execute("SELECT 1 FROM m10_lesson_plans WHERE lesson_plan_id = ? AND owner_id = ?", (item.object_id, item.owner_id)).fetchone()
                if exists is None:
                    continue
                connection.execute("DELETE FROM m10_lesson_versions WHERE lesson_plan_id = ? AND owner_id = ?", (item.object_id, item.owner_id))
                connection.execute("DELETE FROM m10_lesson_plans WHERE lesson_plan_id = ? AND owner_id = ?", (item.object_id, item.owner_id))
                removed += 1
        return removed

    @staticmethod
    def _unlink(parent: Path, stored_name: str) -> None:
        candidate = (parent / stored_name).resolve()
        if candidate.parent != parent.resolve():
            raise ValueError("RESTORE_DELETION_PATH_INVALID")
        candidate.unlink(missing_ok=True)

    @staticmethod
    def _remove_flat_directory(directory: Path, parent: Path) -> None:
        if not directory.exists():
            return
        resolved = directory.resolve()
        if resolved.parent != parent.resolve() or directory.is_symlink():
            raise ValueError("RESTORE_DELETION_PATH_INVALID")
        files = list(directory.iterdir())
        if any(path.is_symlink() or not path.is_file() for path in files):
            raise ValueError("RESTORE_DELETION_PATH_INVALID")
        for path in files:
            path.unlink()
        directory.rmdir()
