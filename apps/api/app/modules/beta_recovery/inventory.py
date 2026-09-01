from __future__ import annotations

from app.core.config import Settings
from app.modules.beta_recovery.recovery import OwnerStoreSource


def owner_store_sources(settings: Settings) -> tuple[OwnerStoreSource, ...]:
    """Durable owner-bearing stores included in the Closed Beta backup set.

    The revocable Beta session database is intentionally excluded: restoring it could
    revive obsolete sessions. Derived similarity indexes and generated exports can be
    rebuilt and are also excluded.
    """

    return (
        OwnerStoreSource("question_bank", "sqlite", settings.question_bank_db),
        OwnerStoreSource("question_media", "directory", settings.question_media_dir),
        OwnerStoreSource("private_library", "sqlite", settings.private_library_db),
        OwnerStoreSource("private_library_files", "directory", settings.private_library_dir),
        OwnerStoreSource("question_capture", "sqlite", settings.question_capture_db),
        OwnerStoreSource("question_capture_files", "directory", settings.question_capture_dir),
        OwnerStoreSource(
            "personal_question_library",
            "sqlite",
            settings.personal_question_library_db,
        ),
        OwnerStoreSource("pdf_imports", "sqlite", settings.pdf_import_db),
        OwnerStoreSource("pdf_import_files", "directory", settings.pdf_import_dir),
        OwnerStoreSource("lesson_plans", "sqlite", settings.lesson_plan_db),
        OwnerStoreSource("exam_papers", "sqlite", settings.exam_paper_db),
        OwnerStoreSource("exam_paper_assets", "directory", settings.exam_paper_asset_dir),
        OwnerStoreSource("teacher_memory", "sqlite", settings.teacher_memory_db),
    )
