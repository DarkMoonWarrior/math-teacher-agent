from __future__ import annotations

import json
import shutil
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.deletion import is_link_or_reparse
from app.modules.exam_papers.schemas import (
    ExamPaperBreakdownItem,
    ExamPaperCreateCommand,
    ExamPaperHistoryRevisionCommand,
    ExamPaperImageSnapshot,
    ExamPaperItemInput,
    ExamPaperItemView,
    ExamPaperLifecycleCommand,
    ExamPaperList,
    ExamPaperOptionSnapshot,
    ExamPaperQuestionSnapshot,
    ExamPaperSummary,
    ExamPaperUpdateCommand,
    ExamPaperView,
    PaperBidirectionalSpecification,
    PaperSpecificationForwardRow,
    PaperSpecificationReverseRow,
)
from app.modules.question_bank import QuestionBank
from app.modules.question_bank.schemas import QuestionDetail


class ExamPaperStudioError(ValueError):
    pass


class ExamPaperStudioConflict(ExamPaperStudioError):
    pass


@dataclass(frozen=True)
class ExamPaperSaveContext:
    """Server-resolved facts used when saving a controlled Paper Agent draft."""

    question_source: object
    section_by_question: dict[str, tuple[str, str]] = field(default_factory=dict)
    specification: PaperBidirectionalSpecification | None = None


class ExamPaperStudio:
    """Deep module for immutable question snapshots and versioned paper drafts."""

    def __init__(
        self,
        *,
        database_path: Path,
        asset_root: Path,
        question_bank: QuestionBank,
    ) -> None:
        self.database_path = database_path
        self.asset_root = asset_root.resolve()
        self.question_bank = question_bank
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.asset_root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create(
        self,
        command: ExamPaperCreateCommand,
        *,
        save_context: ExamPaperSaveContext | None = None,
    ) -> ExamPaperView:
        self._validate_item_inputs(command.items)
        paper_id = f"ep_{uuid4().hex[:12]}"
        now = self._now()
        created_files: list[Path] = []
        question_source = save_context.question_source if save_context else self.question_bank
        section_by_question = save_context.section_by_question if save_context else {}
        try:
            items = [
                self._snapshot_item(
                    paper_id=paper_id,
                    position=index,
                    item_input=item_input,
                    created_files=created_files,
                    question_source=question_source,
                    section=section_by_question.get(item_input.question_id),
                )
                for index, item_input in enumerate(command.items, start=1)
            ]
            paper = self._build_view(
                paper_id=paper_id,
                version=1,
                title=command.title.strip(),
                duration_minutes=command.duration_minutes,
                instructions=command.instructions.strip(),
                items=items,
                specification=save_context.specification if save_context else None,
                created_at=now,
                updated_at=now,
            )
            with self._connect() as connection:
                self._insert_current(connection, paper, command.teacher_id)
                self._insert_revision(connection, paper, command.teacher_id, command.teacher_id)
        except Exception:
            for path in created_files:
                path.unlink(missing_ok=True)
            raise
        return paper

    def update(self, paper_id: str, command: ExamPaperUpdateCommand) -> ExamPaperView:
        self._validate_item_inputs(command.items)
        current = self.get(paper_id)
        existing = {item.question.question_id: item for item in current.items}
        created_files: list[Path] = []
        try:
            items: list[ExamPaperItemView] = []
            for position, item_input in enumerate(command.items, start=1):
                if item_input.question_id in existing:
                    prior = existing[item_input.question_id]
                    items.append(
                        prior.model_copy(
                            update={"position": position, "score": item_input.score}
                        )
                    )
                else:
                    items.append(
                        self._snapshot_item(
                            paper_id=paper_id,
                            position=position,
                            item_input=item_input,
                            created_files=created_files,
                            question_source=self.question_bank,
                            section=None,
                        )
                    )
            updated = self._build_view(
                paper_id=paper_id,
                version=current.version + 1,
                title=command.title.strip(),
                duration_minutes=command.duration_minutes,
                instructions=command.instructions.strip(),
                items=items,
                specification=None,
                created_at=current.created_at,
                updated_at=self._now(),
            )
            with self._connect() as connection:
                self._update_current(connection, updated)
                self._insert_revision(connection, updated, command.teacher_id, command.teacher_id)
        except Exception:
            for path in created_files:
                path.unlink(missing_ok=True)
            raise
        return updated

    def revise_owned_history(
        self,
        paper_id: str,
        command: ExamPaperHistoryRevisionCommand,
        *,
        owner_id: str,
        added_question_source: object | None = None,
    ) -> ExamPaperView:
        """Creates a new owner-scoped revision from an existing saved snapshot.

        Historical editing may reorder, remove, regroup and rescore snapshotted
        questions. Newly added questions must be supplied by a server-resolved
        source that has re-applied the current trust and owner gates.
        """

        current = self.get_owned(paper_id, owner_id=owner_id)
        if current.lifecycle_state != "active":
            raise ExamPaperStudioError("回收站中的试卷需要先恢复后再编辑")
        if current.version != command.expected_version:
            raise ExamPaperStudioConflict("试卷已产生更新版本，请重新打开后再编辑")
        existing = {item.question.question_id: item for item in current.items}
        new_ids = [item.question_id for item in command.items if item.question_id not in existing]
        if new_ids and added_question_source is None:
            raise ExamPaperStudioError("新增题目必须先通过服务端受控题库门禁")

        created_files: list[Path] = []
        try:
            items: list[ExamPaperItemView] = []
            for position, item in enumerate(command.items, start=1):
                if item.question_id in existing:
                    paper_item = existing[item.question_id].model_copy(
                        update={
                            "position": position,
                            "section_id": item.section_id,
                            "section_title": item.section_title.strip(),
                            "score": item.score,
                        }
                    )
                else:
                    paper_item = self._snapshot_item(
                        paper_id=paper_id,
                        position=position,
                        item_input=ExamPaperItemInput(
                            question_id=item.question_id,
                            score=item.score,
                        ),
                        created_files=created_files,
                        question_source=added_question_source,
                        section=None,
                    ).model_copy(
                        update={
                            "section_id": item.section_id,
                            "section_title": item.section_title.strip(),
                        }
                    )
                items.append(paper_item)
            updated = self._build_view(
                paper_id=paper_id,
                version=current.version + 1,
                title=command.title.strip(),
                duration_minutes=command.duration_minutes,
                instructions=command.instructions.strip(),
                items=items,
                specification=self._specification_from_snapshot(items, current.specification),
                created_at=current.created_at,
                updated_at=self._now(),
            )
            with self._connect() as connection:
                cursor = connection.execute(
                """
                UPDATE exam_papers SET version = ?, title = ?, duration_minutes = ?,
                    total_score = ?, question_count = ?, raw_json = ?, updated_at = ?
                WHERE exam_paper_id = ? AND owner_id = ? AND version = ?
                """,
                (
                    updated.version,
                    updated.title,
                    updated.duration_minutes,
                    updated.total_score,
                    len(updated.items),
                    updated.model_dump_json(),
                    updated.updated_at,
                    paper_id,
                    owner_id,
                    current.version,
                ),
            )
                if cursor.rowcount != 1:
                    raise ExamPaperStudioConflict("试卷已产生更新版本，请重新打开后再编辑")
                self._insert_revision(connection, updated, owner_id, owner_id)
        except Exception:
            for path in created_files:
                path.unlink(missing_ok=True)
            raise
        return updated

    def get(self, paper_id: str) -> ExamPaperView:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT raw_json FROM exam_papers WHERE exam_paper_id = ?", (paper_id,)
            ).fetchone()
        if row is None:
            raise KeyError(paper_id)
        return ExamPaperView.model_validate_json(row["raw_json"])

    def get_owned(self, paper_id: str, *, owner_id: str) -> ExamPaperView:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT raw_json FROM exam_papers WHERE exam_paper_id = ? AND owner_id = ?",
                (paper_id, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(paper_id)
        return ExamPaperView.model_validate_json(row["raw_json"])

    def get_owned_version(
        self,
        paper_id: str,
        version: int,
        *,
        owner_id: str,
    ) -> ExamPaperView:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT raw_json FROM exam_paper_revisions
                WHERE exam_paper_id = ? AND version = ? AND owner_id = ?
                """,
                (paper_id, version, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"{paper_id}:v{version}")
        return ExamPaperView.model_validate_json(row["raw_json"])

    def list(self, *, limit: int = 30, lifecycle_state: str = "active") -> ExamPaperList:
        if lifecycle_state not in {"active", "trashed"}:
            raise ExamPaperStudioError("不支持的试卷状态")
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM exam_papers WHERE lifecycle_state = ?", (lifecycle_state,)).fetchone()[0]
            rows = connection.execute(
                """
                SELECT exam_paper_id, title, status, version, duration_minutes,
                       total_score, question_count, updated_at, lifecycle_state, trashed_at
                FROM exam_papers WHERE lifecycle_state = ? ORDER BY updated_at DESC LIMIT ?
                """,
                (lifecycle_state, limit),
            ).fetchall()
        return ExamPaperList(
            items=[ExamPaperSummary(**dict(row)) for row in rows], total=total
        )

    def list_owned(
        self,
        *,
        owner_id: str,
        limit: int = 30,
        lifecycle_state: str = "active",
    ) -> ExamPaperList:
        """Lists only papers belonging to the authenticated teacher."""

        if lifecycle_state not in {"active", "trashed"}:
            raise ExamPaperStudioError("不支持的试卷状态")
        with self._connect() as connection:
            total = connection.execute(
                """
                SELECT COUNT(*) FROM exam_papers
                WHERE owner_id = ? AND lifecycle_state = ?
                """,
                (owner_id, lifecycle_state),
            ).fetchone()[0]
            rows = connection.execute(
                """
                SELECT exam_paper_id, title, status, version, duration_minutes,
                       total_score, question_count, updated_at, lifecycle_state, trashed_at
                FROM exam_papers
                WHERE owner_id = ? AND lifecycle_state = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (owner_id, lifecycle_state, limit),
            ).fetchall()
        return ExamPaperList(
            items=[ExamPaperSummary(**dict(row)) for row in rows], total=total
        )

    def change_lifecycle(self, paper_id: str, command: ExamPaperLifecycleCommand) -> ExamPaperView:
        current = self.get(paper_id)
        target = "trashed" if command.action == "trash" else "active"
        now = self._now()
        updated = current.model_copy(update={"lifecycle_state": target, "trashed_at": now if target == "trashed" else None, "updated_at": now})
        with self._connect() as connection:
            connection.execute("UPDATE exam_papers SET lifecycle_state = ?, trashed_at = ?, raw_json = ?, updated_at = ? WHERE exam_paper_id = ?", (target, updated.trashed_at, updated.model_dump_json(), now, paper_id))
        return updated

    def change_owned_lifecycle(
        self,
        paper_id: str,
        command: ExamPaperLifecycleCommand,
        *,
        owner_id: str,
    ) -> ExamPaperView:
        """Moves only the current teacher's paper between history and recycle bin."""

        current = self.get_owned(paper_id, owner_id=owner_id)
        target = "trashed" if command.action == "trash" else "active"
        now = self._now()
        updated = current.model_copy(
            update={
                "lifecycle_state": target,
                "trashed_at": now if target == "trashed" else None,
                "updated_at": now,
            }
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE exam_papers
                SET lifecycle_state = ?, trashed_at = ?, raw_json = ?, updated_at = ?
                WHERE exam_paper_id = ? AND owner_id = ?
                """,
                (
                    target,
                    updated.trashed_at,
                    updated.model_dump_json(),
                    now,
                    paper_id,
                    owner_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(paper_id)
        return updated

    def permanently_delete_owned(
        self,
        paper_id: str,
        *,
        owner_id: str,
        expected_updated_at: str,
    ) -> None:
        """Delete one trashed paper snapshot without touching its source questions."""

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT lifecycle_state, updated_at FROM exam_papers
                   WHERE exam_paper_id = ? AND owner_id = ?""",
                (paper_id, owner_id),
            ).fetchone()
            if row is None:
                raise KeyError(paper_id)
            if row["lifecycle_state"] != "trashed":
                raise ExamPaperStudioConflict("试卷必须先移入回收站")
            if row["updated_at"] != expected_updated_at:
                raise ExamPaperStudioConflict("试卷已发生变化，请刷新后重试")
            connection.execute(
                "DELETE FROM exam_paper_revisions WHERE exam_paper_id = ? AND owner_id = ?",
                (paper_id, owner_id),
            )
            cursor = connection.execute(
                "DELETE FROM exam_papers WHERE exam_paper_id = ? AND owner_id = ?",
                (paper_id, owner_id),
            )
            if cursor.rowcount != 1:  # pragma: no cover - transaction safety
                raise ExamPaperStudioConflict("试卷活动存储不完整，已取消永久删除")
            self._remove_owned_asset_directory(paper_id)

    def _remove_owned_asset_directory(self, paper_id: str) -> None:
        asset_dir = self.asset_root / paper_id
        if not asset_dir.exists():
            return
        resolved_root = self.asset_root.resolve()
        resolved_dir = asset_dir.resolve()
        if resolved_dir.parent != resolved_root or is_link_or_reparse(asset_dir):
            raise ExamPaperStudioConflict("试卷资源目录不安全，已取消永久删除")
        files = list(asset_dir.iterdir())
        if any(is_link_or_reparse(path) or not path.is_file() for path in files):
            raise ExamPaperStudioConflict("试卷资源目录不完整，已取消永久删除")
        for path in files:
            path.unlink()
        asset_dir.rmdir()

    def asset_path(self, paper_id: str, asset_id: str) -> Path:
        paper = self.get(paper_id)
        asset = next(
            (
                image
                for item in paper.items
                for image in item.question.images
                if image.asset_id == asset_id
            ),
            None,
        )
        if asset is None:
            raise KeyError(asset_id)
        matches = list((self.asset_root / paper_id).glob(f"{asset_id}.*"))
        if len(matches) != 1:
            raise KeyError(asset_id)
        path = matches[0].resolve()
        if self.asset_root not in path.parents or not path.is_file():
            raise KeyError(asset_id)
        return path

    def _snapshot_item(
        self,
        *,
        paper_id: str,
        position: int,
        item_input: ExamPaperItemInput,
        created_files: list[Path],
        question_source,
        section: tuple[str, str] | None,
    ) -> ExamPaperItemView:
        try:
            detail = question_source.get_question(item_input.question_id)
        except KeyError as exc:
            raise ExamPaperStudioError(f"题目不存在：{item_input.question_id}") from exc
        if detail.verification_status not in {
            "passed",
            "math_verifier_passed",
            "authoring_checks_passed_teacher_review_required",
        }:
            raise ExamPaperStudioError(
                f"题目 {item_input.question_id} 尚未通过独立数学验证，不能加入试卷"
            )
        if detail.status == "rejected" or detail.review_status == "rejected":
            raise ExamPaperStudioError(f"题目 {item_input.question_id} 已被拒绝，不能加入试卷")
        snapshot = self._snapshot_question(
            paper_id=paper_id,
            detail=detail,
            created_files=created_files,
            question_source=question_source,
        )
        return ExamPaperItemView(
            item_id=f"epi_{uuid4().hex[:16]}",
            position=position,
            section_id=section[0] if section else None,
            section_title=section[1] if section else self._section_title(detail.question_type),
            score=item_input.score,
            question=snapshot,
        )

    def _snapshot_question(
        self,
        *,
        paper_id: str,
        detail: QuestionDetail,
        created_files: list[Path],
        question_source,
    ) -> ExamPaperQuestionSnapshot:
        raw = detail.raw
        solution = (raw.get("solutions") or [{}])[0]
        images: list[ExamPaperImageSnapshot] = []
        paper_asset_dir = self.asset_root / paper_id
        paper_asset_dir.mkdir(parents=True, exist_ok=True)
        for image in detail.images:
            if image.placement != "stem":
                continue
            source_path, _ = question_source.image_path(detail.question_id, image.image_id)
            asset_id = f"epa_{uuid4().hex}"
            target_path = paper_asset_dir / f"{asset_id}{source_path.suffix.lower()}"
            shutil.copyfile(source_path, target_path)
            created_files.append(target_path)
            images.append(
                ExamPaperImageSnapshot(
                    asset_id=asset_id,
                    original_filename=image.original_filename,
                    mime_type=image.mime_type,
                    width=image.width,
                    height=image.height,
                    alt_text=image.alt_text,
                    caption=image.caption,
                )
            )
        return ExamPaperQuestionSnapshot(
            question_id=detail.question_id,
            source_revision_count=detail.revision_count,
            question_type=detail.question_type,
            stem_plain=detail.stem_plain,
            stem_latex=(raw.get("stem") or {}).get("latex"),
            options=[
                ExamPaperOptionSnapshot(
                    key=str(option.get("key", "")),
                    text=str(option.get("latex") or option.get("plain_text") or ""),
                )
                for option in raw.get("options") or []
            ],
            answer_value=detail.answer_value,
            solution_method=solution.get("method"),
            solution_steps=[str(item) for item in solution.get("steps_latex") or []],
            final_answer=solution.get("final_answer"),
            solution_status=(
                solution.get("solution_status")
                if solution.get("solution_status") in {"ready", "needs_teacher_verification"}
                else "ready"
            ),
            solution_issue=solution.get("solution_issue"),
            volume=detail.volume,
            chapter=detail.chapter,
            section=detail.section,
            knowledge_point_ids=detail.knowledge_point_ids,
            difficulty=detail.difficulty,
            verification_status=detail.verification_status,
            review_status=detail.review_status,
            source_document=detail.source_document,
            license_status=detail.license_status,
            images=images,
        )

    def _build_view(
        self,
        *,
        paper_id: str,
        version: int,
        title: str,
        duration_minutes: int,
        instructions: str,
        items: list[ExamPaperItemView],
        specification: PaperBidirectionalSpecification | None,
        created_at: str,
        updated_at: str,
    ) -> ExamPaperView:
        warnings = ["试卷采用题目版本快照；题库后续修订不会自动改变本试卷。"]
        pending_review = sum(
            item.question.review_status not in {"approved", "owner_saved_complete"}
            for item in items
        )
        if pending_review:
            warnings.append(f"其中 {pending_review} 道题已通过数学验证，但仍待教师完成内容审核。")
        if any(item.question.images for item in items):
            warnings.append("题干图片已复制为试卷独立资产，导出前请复核图文对应关系。")
        return ExamPaperView(
            exam_paper_id=paper_id,
            version=version,
            title=title,
            duration_minutes=duration_minutes,
            instructions=instructions,
            total_score=round(sum(item.score for item in items), 2),
            items=items,
            chapter_breakdown=self._breakdown(
                (item.question.chapter or "未分类", item.score) for item in items
            ),
            difficulty_breakdown=self._breakdown(
                (f"难度 {item.question.difficulty}", item.score) for item in items
            ),
            specification=specification,
            warnings=warnings,
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _breakdown(rows) -> list[ExamPaperBreakdownItem]:
        grouped: dict[str, list[float]] = defaultdict(list)
        for label, score in rows:
            grouped[label].append(score)
        return [
            ExamPaperBreakdownItem(
                label=label,
                question_count=len(scores),
                score=round(sum(scores), 2),
            )
            for label, scores in grouped.items()
        ]

    @staticmethod
    def _specification_from_snapshot(
        items: list[ExamPaperItemView],
        previous: PaperBidirectionalSpecification | None,
    ) -> PaperBidirectionalSpecification:
        source_kind_by_question = {
            row.question_id: row.source_kind
            for row in (previous.question_to_dimensions if previous else [])
        }
        forward = [
            PaperSpecificationForwardRow(
                position=item.position,
                question_id=item.question.question_id,
                section_title=item.section_title,
                question_type=item.question.question_type,
                chapter=item.question.chapter or "未分类",
                knowledge_points=item.question.knowledge_point_ids or ["未标注"],
                difficulty=item.question.difficulty,
                score=item.score,
                verification_status=item.question.verification_status,
                review_status=item.question.review_status,
                source_kind=source_kind_by_question.get(
                    item.question.question_id,
                    "public_question_bank",
                ),
            )
            for item in items
        ]
        grouped: dict[tuple[str, str], list[ExamPaperItemView]] = defaultdict(list)
        for item in items:
            grouped[("section", item.section_title)].append(item)
            grouped[("question_type", item.question.question_type)].append(item)
            grouped[("difficulty", f"难度 {item.question.difficulty}")].append(item)
            for point in item.question.knowledge_point_ids or ["未标注"]:
                grouped[("knowledge_point", point)].append(item)
        dimension_order = {"section": 0, "question_type": 1, "knowledge_point": 2, "difficulty": 3}
        reverse = []
        for (dimension, label), grouped_items in sorted(
            grouped.items(),
            key=lambda row: (
                dimension_order[row[0][0]],
                min(item.position for item in row[1]),
                row[0][1],
            ),
        ):
            ordered = sorted(grouped_items, key=lambda item: item.position)
            reverse.append(
                PaperSpecificationReverseRow(
                    dimension=dimension,
                    label=label,
                    positions=[item.position for item in ordered],
                    question_ids=[item.question.question_id for item in ordered],
                    question_count=len(ordered),
                    score=round(sum(item.score for item in ordered), 2),
                )
            )
        return PaperBidirectionalSpecification(
            question_to_dimensions=forward,
            dimension_to_questions=reverse,
        )

    @staticmethod
    def _validate_item_inputs(items: list[ExamPaperItemInput]) -> None:
        ids = [item.question_id for item in items]
        if len(ids) != len(set(ids)):
            raise ExamPaperStudioError("同一份试卷不能重复加入同一道题")

    @staticmethod
    def _section_title(question_type: str) -> str:
        return {
            "single_choice": "一、单项选择题",
            "multiple_choice": "二、多项选择题",
            "fill_blank": "三、填空题",
        }.get(question_type, "四、解答题")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS exam_papers (
                    exam_paper_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    total_score REAL NOT NULL,
                    question_count INTEGER NOT NULL,
                    owner_id TEXT NOT NULL DEFAULT 'owner_teacher',
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                    , lifecycle_state TEXT NOT NULL DEFAULT 'active', trashed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS exam_paper_revisions (
                    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_paper_id TEXT NOT NULL REFERENCES exam_papers(exam_paper_id),
                    version INTEGER NOT NULL,
                    editor_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL DEFAULT 'owner_teacher',
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(exam_paper_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_exam_papers_updated
                ON exam_papers(updated_at DESC);
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(exam_papers)")}
            if "lifecycle_state" not in columns:
                connection.execute("ALTER TABLE exam_papers ADD COLUMN lifecycle_state TEXT NOT NULL DEFAULT 'active'")
            if "trashed_at" not in columns:
                connection.execute("ALTER TABLE exam_papers ADD COLUMN trashed_at TEXT")
            if "owner_id" not in columns:
                connection.execute(
                    "ALTER TABLE exam_papers ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'owner_teacher'"
                )
            revision_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(exam_paper_revisions)")
            }
            if "owner_id" not in revision_columns:
                connection.execute(
                    "ALTER TABLE exam_paper_revisions ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'owner_teacher'"
                )

    @staticmethod
    def _insert_current(
        connection: sqlite3.Connection,
        paper: ExamPaperView,
        owner_id: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO exam_papers
            (exam_paper_id, status, version, title, duration_minutes, total_score,
             question_count, owner_id, raw_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper.exam_paper_id,
                paper.status,
                paper.version,
                paper.title,
                paper.duration_minutes,
                paper.total_score,
                len(paper.items),
                owner_id,
                paper.model_dump_json(),
                paper.created_at,
                paper.updated_at,
            ),
        )

    @staticmethod
    def _update_current(connection: sqlite3.Connection, paper: ExamPaperView) -> None:
        connection.execute(
            """
            UPDATE exam_papers SET version = ?, title = ?, duration_minutes = ?,
                total_score = ?, question_count = ?, raw_json = ?, updated_at = ?
            WHERE exam_paper_id = ?
            """,
            (
                paper.version,
                paper.title,
                paper.duration_minutes,
                paper.total_score,
                len(paper.items),
                paper.model_dump_json(),
                paper.updated_at,
                paper.exam_paper_id,
            ),
        )

    @staticmethod
    def _insert_revision(
        connection: sqlite3.Connection,
        paper: ExamPaperView,
        editor_id: str,
        owner_id: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO exam_paper_revisions
            (exam_paper_id, version, editor_id, owner_id, raw_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                paper.exam_paper_id,
                paper.version,
                editor_id,
                owner_id,
                paper.model_dump_json(),
                paper.updated_at,
            ),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
