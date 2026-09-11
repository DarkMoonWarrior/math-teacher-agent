from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from app.modules.tenant_migration.file_reconciliation import (
    OwnerFileReconciliation,
    OwnerFileStoreSpec,
)
from app.modules.tenant_migration.fingerprints import (
    OwnerMigrationFingerprintError,
    canonical_digest,
    canonical_sqlite_value,
    owner_file_digest,
    owner_object_digest,
    source_record_fingerprint,
    target_binding_fingerprint,
)
from app.modules.tenant_migration.inventory import (
    OwnerDataInventory,
    OwnerDirectoryStoreSpec,
    OwnerSqliteStoreSpec,
    OwnerStoreSpec,
)
from app.modules.tenant_migration.schemas import (
    OwnerDataInventoryReport,
    OwnerFileReconciliationReport,
    OwnerMigrationFilePlan,
    OwnerMigrationObjectPlan,
    OwnerMigrationPlanReport,
    OwnerMigrationTablePlan,
)


class OwnerMigrationPlanningError(ValueError):
    """The requested read-only migration plan cannot be proven safe."""


@dataclass(frozen=True)
class OwnerMigrationDependency:
    table_name: str
    key_columns: tuple[str, ...]


@dataclass(frozen=True)
class OwnerMigrationQuerySpec:
    store_id: str
    table_name: str
    ownership: Literal["direct", "inherited"]
    key_columns: tuple[str, ...]
    query: str
    dependencies: tuple[OwnerMigrationDependency, ...] = ()
    owner_columns: int = 1


def _dependency(table_name: str, *key_columns: str) -> OwnerMigrationDependency:
    return OwnerMigrationDependency(table_name, key_columns)


def _direct(
    store_id: str,
    table_name: str,
    *key_columns: str,
) -> OwnerMigrationQuerySpec:
    selected = ", ".join(f't."{column}"' for column in key_columns)
    return OwnerMigrationQuerySpec(
        store_id,
        table_name,
        "direct",
        key_columns,
        f'SELECT {selected}, t.owner_id FROM "{table_name}" t',
    )


def owner_migration_query_specs() -> tuple[OwnerMigrationQuerySpec, ...]:
    """Return the fixed ownership graph used only for read-only planning."""

    specs: list[OwnerMigrationQuerySpec] = [
        _direct("private_library", "library_items", "library_item_id"),
        _direct("question_capture", "question_capture_assets", "asset_id"),
        _direct(
            "personal_question_library",
            "personal_question_collections",
            "collection_id",
        ),
        _direct(
            "personal_question_library", "personal_authoring_drafts", "draft_id"
        ),
        _direct("pdf_imports", "import_batches", "batch_id"),
        _direct("lesson_plans", "m10_lesson_plans", "lesson_plan_id"),
        _direct("exam_papers", "exam_papers", "exam_paper_id"),
        _direct("teacher_memory", "m11_teacher_memory_profiles", "owner_id"),
        _direct(
            "teacher_memory",
            "m11_teacher_preferences",
            "owner_id",
            "preference_key",
        ),
        _direct(
            "teacher_memory",
            "m11_teacher_memory_observations",
            "owner_id",
            "evidence_id",
            "preference_key",
        ),
        _direct(
            "teacher_memory",
            "m11_teacher_memory_proposals",
            "owner_id",
            "proposal_id",
        ),
        _direct(
            "teacher_memory", "m11_teacher_memory_feedback", "feedback_id"
        ),
    ]
    for table_name, key_columns in (
        ("library_text_revisions", ("revision_id",)),
        ("library_ocr_runs", ("run_id",)),
        ("library_question_candidates", ("candidate_id",)),
        ("library_lifecycle_events", ("event_id",)),
    ):
        keys = ", ".join(f'c."{column}"' for column in key_columns)
        specs.append(
            OwnerMigrationQuerySpec(
                "private_library",
                table_name,
                "inherited",
                key_columns,
                f'SELECT {keys}, p.library_item_id, p.owner_id '
                f'FROM "{table_name}" c LEFT JOIN library_items p '
                "ON p.library_item_id = c.library_item_id",
                (_dependency("library_items", "library_item_id"),),
            )
        )
    for table_name, key_columns in (
        ("question_capture_revisions", ("asset_id", "revision")),
        (
            "question_capture_recognitions",
            ("asset_id", "recognition_revision"),
        ),
    ):
        keys = ", ".join(f'c."{column}"' for column in key_columns)
        specs.append(
            OwnerMigrationQuerySpec(
                "question_capture",
                table_name,
                "inherited",
                key_columns,
                f'SELECT {keys}, p.asset_id, p.owner_id '
                f'FROM "{table_name}" c LEFT JOIN question_capture_assets p '
                "ON p.asset_id = c.asset_id",
                (_dependency("question_capture_assets", "asset_id"),),
            )
        )
    specs.extend(
        (
            OwnerMigrationQuerySpec(
                "question_capture",
                "question_capture_solve_uses",
                "direct",
                ("request_id",),
                "SELECT c.request_id, p.asset_id, c.owner_id, p.owner_id "
                "FROM question_capture_solve_uses c "
                "LEFT JOIN question_capture_assets p ON p.asset_id = c.asset_id",
                (_dependency("question_capture_assets", "asset_id"),),
                2,
            ),
            OwnerMigrationQuerySpec(
                "personal_question_library",
                "personal_question_categories",
                "direct",
                ("category_id",),
                "SELECT c.category_id, p.collection_id, c.owner_id, p.owner_id "
                "FROM personal_question_categories c "
                "LEFT JOIN personal_question_collections p "
                "ON p.collection_id = c.collection_id",
                (_dependency("personal_question_collections", "collection_id"),),
                2,
            ),
            OwnerMigrationQuerySpec(
                "personal_question_library",
                "personal_authoring_revisions",
                "direct",
                ("draft_id", "revision_number"),
                "SELECT r.draft_id, r.revision_number, d.draft_id, "
                "r.owner_id, d.owner_id FROM personal_authoring_revisions r "
                "LEFT JOIN personal_authoring_drafts d ON d.draft_id = r.draft_id",
                (_dependency("personal_authoring_drafts", "draft_id"),),
                2,
            ),
            OwnerMigrationQuerySpec(
                "personal_question_library",
                "personal_questions",
                "direct",
                ("question_id",),
                "SELECT q.question_id, c.collection_id, k.category_id, d.draft_id, "
                "q.owner_id, c.owner_id, k.owner_id, d.owner_id "
                "FROM personal_questions q "
                "LEFT JOIN personal_question_collections c "
                "ON c.collection_id = q.collection_id "
                "LEFT JOIN personal_question_categories k "
                "ON k.category_id = q.category_id "
                "LEFT JOIN personal_authoring_drafts d "
                "ON d.draft_id = q.source_draft_id",
                (
                    _dependency("personal_question_collections", "collection_id"),
                    _dependency("personal_question_categories", "category_id"),
                    _dependency("personal_authoring_drafts", "draft_id"),
                ),
                4,
            ),
        )
    )
    specs.extend(_pdf_query_specs())
    specs.extend(
        (
            OwnerMigrationQuerySpec(
                "lesson_plans",
                "m10_lesson_versions",
                "direct",
                ("lesson_plan_id", "version"),
                "SELECT v.lesson_plan_id, v.version, p.lesson_plan_id, "
                "v.owner_id, p.owner_id FROM m10_lesson_versions v "
                "LEFT JOIN m10_lesson_plans p "
                "ON p.lesson_plan_id = v.lesson_plan_id",
                (_dependency("m10_lesson_plans", "lesson_plan_id"),),
                2,
            ),
            OwnerMigrationQuerySpec(
                "exam_papers",
                "exam_paper_revisions",
                "direct",
                ("exam_paper_id", "version"),
                "SELECT r.exam_paper_id, r.version, p.exam_paper_id, "
                "r.owner_id, p.owner_id FROM exam_paper_revisions r "
                "LEFT JOIN exam_papers p ON p.exam_paper_id = r.exam_paper_id",
                (_dependency("exam_papers", "exam_paper_id"),),
                2,
            ),
        )
    )
    return tuple(specs)


def _pdf_query_specs() -> tuple[OwnerMigrationQuerySpec, ...]:
    batch = _dependency("import_batches", "batch_id")
    file = _dependency("import_files", "file_id")
    pair = _dependency("import_source_pairs", "pair_id")
    boundary = _dependency("import_boundary_candidates", "candidate_id")
    draft = _dependency("import_structured_question_drafts", "draft_id")
    return (
        OwnerMigrationQuerySpec(
            "pdf_imports",
            "import_files",
            "inherited",
            ("file_id",),
            "SELECT f.file_id, b.batch_id, b.owner_id FROM import_files f "
            "LEFT JOIN import_batches b ON b.batch_id = f.batch_id",
            (batch,),
        ),
        OwnerMigrationQuerySpec(
            "pdf_imports",
            "import_file_lifecycle_events",
            "inherited",
            ("event_id",),
            "SELECT e.event_id, f.file_id, b.owner_id "
            "FROM import_file_lifecycle_events e "
            "LEFT JOIN import_files f ON f.file_id = e.file_id "
            "LEFT JOIN import_batches b ON b.batch_id = f.batch_id",
            (file,),
        ),
        OwnerMigrationQuerySpec(
            "pdf_imports",
            "import_batch_lifecycle_events",
            "inherited",
            ("event_id",),
            "SELECT e.event_id, b.batch_id, b.owner_id "
            "FROM import_batch_lifecycle_events e "
            "LEFT JOIN import_batches b ON b.batch_id = e.batch_id",
            (batch,),
        ),
        OwnerMigrationQuerySpec(
            "pdf_imports",
            "import_pages",
            "inherited",
            ("page_id",),
            "SELECT p.page_id, f.file_id, b.owner_id FROM import_pages p "
            "LEFT JOIN import_files f ON f.file_id = p.file_id "
            "LEFT JOIN import_batches b ON b.batch_id = f.batch_id",
            (file,),
        ),
        OwnerMigrationQuerySpec(
            "pdf_imports",
            "import_source_pairs",
            "inherited",
            ("pair_id",),
            "SELECT p.pair_id, q.file_id, s.file_id, qb.owner_id, sb.owner_id "
            "FROM import_source_pairs p "
            "LEFT JOIN import_files q ON q.file_id = p.question_file_id "
            "LEFT JOIN import_batches qb ON qb.batch_id = q.batch_id "
            "LEFT JOIN import_files s ON s.file_id = p.solution_file_id "
            "LEFT JOIN import_batches sb ON sb.batch_id = s.batch_id",
            (file, file),
            2,
        ),
        OwnerMigrationQuerySpec(
            "pdf_imports",
            "import_boundary_candidates",
            "inherited",
            ("candidate_id",),
            "SELECT c.candidate_id, f.file_id, b.owner_id "
            "FROM import_boundary_candidates c "
            "LEFT JOIN import_files f ON f.file_id = c.file_id "
            "LEFT JOIN import_batches b ON b.batch_id = f.batch_id",
            (file,),
        ),
        OwnerMigrationQuerySpec(
            "pdf_imports",
            "import_source_item_matches",
            "inherited",
            ("item_match_id",),
            "SELECT m.item_match_id, p.pair_id, qc.candidate_id, "
            "sc.candidate_id, qb.owner_id, sb.owner_id, "
            "qcb.owner_id, scb.owner_id "
            "FROM import_source_item_matches m "
            "LEFT JOIN import_source_pairs p ON p.pair_id = m.pair_id "
            "LEFT JOIN import_files q ON q.file_id = p.question_file_id "
            "LEFT JOIN import_batches qb ON qb.batch_id = q.batch_id "
            "LEFT JOIN import_files s ON s.file_id = p.solution_file_id "
            "LEFT JOIN import_batches sb ON sb.batch_id = s.batch_id "
            "LEFT JOIN import_boundary_candidates qc "
            "ON qc.candidate_id = m.question_candidate_id "
            "LEFT JOIN import_files qcf ON qcf.file_id = qc.file_id "
            "LEFT JOIN import_batches qcb ON qcb.batch_id = qcf.batch_id "
            "LEFT JOIN import_boundary_candidates sc "
            "ON sc.candidate_id = m.solution_candidate_id "
            "LEFT JOIN import_files scf ON scf.file_id = sc.file_id "
            "LEFT JOIN import_batches scb ON scb.batch_id = scf.batch_id",
            (pair, boundary, boundary),
            4,
        ),
        OwnerMigrationQuerySpec(
            "pdf_imports",
            "import_structured_question_drafts",
            "inherited",
            ("draft_id",),
            "SELECT d.draft_id, f.file_id, c.candidate_id, "
            "b.owner_id, cb.owner_id FROM import_structured_question_drafts d "
            "LEFT JOIN import_files f ON f.file_id = d.file_id "
            "LEFT JOIN import_batches b ON b.batch_id = f.batch_id "
            "LEFT JOIN import_boundary_candidates c "
            "ON c.candidate_id = d.boundary_candidate_id "
            "LEFT JOIN import_files cf ON cf.file_id = c.file_id "
            "LEFT JOIN import_batches cb ON cb.batch_id = cf.batch_id",
            (file, boundary),
            2,
        ),
        OwnerMigrationQuerySpec(
            "pdf_imports",
            "import_structured_media_crops",
            "inherited",
            ("crop_id",),
            "SELECT c.crop_id, d.draft_id, f.file_id, b.owner_id, db.owner_id "
            "FROM import_structured_media_crops c "
            "LEFT JOIN import_structured_question_drafts d "
            "ON d.draft_id = c.draft_id "
            "LEFT JOIN import_files f ON f.file_id = c.file_id "
            "LEFT JOIN import_batches b ON b.batch_id = f.batch_id "
            "LEFT JOIN import_files df ON df.file_id = d.file_id "
            "LEFT JOIN import_batches db ON db.batch_id = df.batch_id",
            (draft, file),
            2,
        ),
    )


class OwnerMigrationPlanner:
    """Build a digest-only object graph; never execute or persist a migration."""

    _FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
    _SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,79}$")

    def __init__(
        self,
        data_specs: tuple[OwnerStoreSpec, ...],
        file_specs: tuple[OwnerFileStoreSpec, ...],
        query_specs: tuple[OwnerMigrationQuerySpec, ...] | None = None,
    ) -> None:
        self._data_specs = data_specs
        self._file_specs = file_specs
        self._query_specs = query_specs or owner_migration_query_specs()
        self._validate_catalog()
        self._inventory = OwnerDataInventory(data_specs)
        self._reconciliation = OwnerFileReconciliation(file_specs)

    def plan(
        self,
        *,
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
        expected_inventory_fingerprint: str,
        expected_file_reconciliation_fingerprint: str,
    ) -> OwnerMigrationPlanReport:
        self._validate_request(
            source_owner_id,
            target_owner_id,
            target_tenant_id,
            expected_inventory_fingerprint,
            expected_file_reconciliation_fingerprint,
        )
        inventory = self._inventory.inspect(source_owner_id=source_owner_id)
        files = self._reconciliation.reconcile(source_owner_id=source_owner_id)
        self._match_evidence(
            inventory.report_fingerprint,
            files.report_fingerprint,
            expected_inventory_fingerprint,
            expected_file_reconciliation_fingerprint,
        )
        self._require_ready_evidence(inventory, files)

        binding = (source_owner_id, target_owner_id, target_tenant_id)
        table_plans = self._table_plans(source_owner_id, binding)
        self._require_closed_object_graph(table_plans)
        file_plans = self._file_plans(source_owner_id, binding, files)

        final_inventory = self._inventory.inspect(source_owner_id=source_owner_id)
        final_files = self._reconciliation.reconcile(source_owner_id=source_owner_id)
        self._match_evidence(
            final_inventory.report_fingerprint,
            final_files.report_fingerprint,
            inventory.report_fingerprint,
            files.report_fingerprint,
        )
        final_table_plans = self._table_plans(source_owner_id, binding)
        self._require_closed_object_graph(final_table_plans)
        final_file_plans = self._file_plans(source_owner_id, binding, final_files)
        if table_plans != final_table_plans or file_plans != final_file_plans:
            raise OwnerMigrationPlanningError("MIGRATION_OBJECTS_CHANGED")
        target_binding = target_binding_fingerprint(
            target_owner_id, target_tenant_id
        )
        canonical = {
            "schema_version": 1,
            "source_inventory_fingerprint": inventory.report_fingerprint,
            "source_file_reconciliation_fingerprint": files.report_fingerprint,
            "target_binding_fingerprint": target_binding,
            "tables": [table.model_dump(mode="json") for table in table_plans],
            "files": [file.model_dump(mode="json") for file in file_plans],
        }
        return OwnerMigrationPlanReport(
            source_inventory_fingerprint=inventory.report_fingerprint,
            source_file_reconciliation_fingerprint=files.report_fingerprint,
            target_binding_fingerprint=target_binding,
            object_count=sum(table.object_count for table in table_plans),
            file_count=sum(file.object_count for file in file_plans),
            plan_fingerprint=self._digest(canonical),
            tables=table_plans,
            files=file_plans,
        )

    def _table_plans(
        self, source_owner_id: str, binding: tuple[str, str, str]
    ) -> tuple[OwnerMigrationTablePlan, ...]:
        stores = {
            spec.store_id: spec
            for spec in self._data_specs
            if isinstance(spec, OwnerSqliteStoreSpec)
        }
        result: list[OwnerMigrationTablePlan] = []
        sequence = 1
        for query_spec in self._query_specs:
            store = stores[query_spec.store_id]
            if not store.path.exists():
                continue
            with self._connect(store.path) as connection:
                if not self._table_exists(connection, query_spec.table_name):
                    continue
                objects = self._query_objects(
                    connection, query_spec, source_owner_id, binding
                )
            result.append(
                OwnerMigrationTablePlan(
                    store_id=query_spec.store_id,
                    table_name=query_spec.table_name,
                    ownership=query_spec.ownership,
                    sequence=sequence,
                    object_count=len(objects),
                    object_set_fingerprint=self._digest(
                        [item.model_dump(mode="json") for item in objects]
                    ),
                    objects=objects,
                )
            )
            sequence += 1
        return tuple(result)

    def _query_objects(
        self,
        connection: sqlite3.Connection,
        spec: OwnerMigrationQuerySpec,
        source_owner_id: str,
        binding: tuple[str, str, str],
    ) -> tuple[OwnerMigrationObjectPlan, ...]:
        expected_width = len(spec.key_columns) + sum(
            len(item.key_columns) for item in spec.dependencies
        ) + spec.owner_columns
        try:
            rows = connection.execute(spec.query).fetchall()
        except sqlite3.Error as error:
            raise OwnerMigrationPlanningError("MIGRATION_QUERY_FAILED") from error
        objects: list[OwnerMigrationObjectPlan] = []
        seen: set[str] = set()
        for row in rows:
            if len(row) != expected_width:
                raise OwnerMigrationPlanningError("MIGRATION_QUERY_SHAPE_INVALID")
            owners = tuple(row[-spec.owner_columns :])
            if (
                len(owners) != spec.owner_columns
                or any(not isinstance(owner, str) or not owner for owner in owners)
                or len(set(owners)) != 1
            ):
                raise OwnerMigrationPlanningError(
                    "MIGRATION_OWNER_RELATIONSHIP_UNRESOLVED"
                )
            cursor = len(spec.key_columns)
            key = tuple(row[:cursor])
            self._validate_key(key)
            dependency_values: list[
                tuple[OwnerMigrationDependency, tuple[object, ...]]
            ] = []
            for dependency in spec.dependencies:
                width = len(dependency.key_columns)
                values = tuple(row[cursor : cursor + width])
                self._validate_key(values)
                dependency_values.append((dependency, values))
                cursor += width
            if owners[0] != source_owner_id:
                continue
            digest = self._object_digest(
                binding, spec.store_id, spec.table_name, key
            )
            if digest in seen:
                raise OwnerMigrationPlanningError("MIGRATION_OBJECT_NOT_UNIQUE")
            seen.add(digest)
            dependencies = tuple(
                self._object_digest(
                    binding, spec.store_id, dependency.table_name, values
                )
                for dependency, values in dependency_values
            )
            objects.append(
                OwnerMigrationObjectPlan(
                    object_digest=digest,
                    source_record_fingerprint=self._record_fingerprint(
                        connection,
                        binding,
                        spec,
                        key,
                    ),
                    dependency_digests=dependencies,
                )
            )
        return tuple(sorted(objects, key=lambda item: item.object_digest))

    def _file_plans(
        self,
        source_owner_id: str,
        binding: tuple[str, str, str],
        reconciliation: OwnerFileReconciliationReport,
    ) -> tuple[OwnerMigrationFilePlan, ...]:
        stores_by_id = {item.store_id: item for item in reconciliation.stores}
        result: list[OwnerMigrationFilePlan] = []
        sequence = len(self._query_specs) + 1
        for spec in self._file_specs:
            references = self._file_references(spec, source_owner_id)
            expected = stores_by_id[spec.store_id].referenced_files
            if len(references) != expected:
                raise OwnerMigrationPlanningError("MIGRATION_FILE_EVIDENCE_MISMATCH")
            digests = tuple(
                sorted(
                    owner_file_digest(binding, spec.store_id, reference)
                    for reference in references
                )
            )
            result.append(
                OwnerMigrationFilePlan(
                    store_id=spec.store_id,
                    sequence=sequence,
                    object_count=len(digests),
                    object_set_fingerprint=self._digest(digests),
                    object_digests=digests,
                )
            )
            sequence += 1
        return tuple(result)

    def _file_references(
        self, spec: OwnerFileStoreSpec, source_owner_id: str
    ) -> set[str]:
        if not spec.database.path.exists():
            return set()
        with self._connect(spec.database.path) as connection:
            if spec.layout == "private_library":
                rows = connection.execute(
                    "SELECT stored_name, owner_id FROM library_items"
                ).fetchall()
                return self._owned_file_rows(rows, source_owner_id, "library")
            if spec.layout == "question_capture":
                rows = connection.execute(
                    "SELECT r.stored_name, a.owner_id "
                    "FROM question_capture_revisions r "
                    "LEFT JOIN question_capture_assets a "
                    "ON a.asset_id = r.asset_id"
                ).fetchall()
                return self._owned_file_rows(rows, source_owner_id, "capture")
            if spec.layout == "pdf_imports":
                files = connection.execute(
                    "SELECT f.stored_name, b.owner_id FROM import_files f "
                    "LEFT JOIN import_batches b ON b.batch_id = f.batch_id"
                ).fetchall()
                crops = connection.execute(
                    "SELECT c.stored_name, b.owner_id "
                    "FROM import_structured_media_crops c "
                    "LEFT JOIN import_files f ON f.file_id = c.file_id "
                    "LEFT JOIN import_batches b ON b.batch_id = f.batch_id"
                ).fetchall()
                return self._owned_file_rows(
                    (*files, *crops), source_owner_id, "pdf"
                )
            if spec.layout == "exam_papers":
                return self._exam_file_references(connection, source_owner_id)
        raise OwnerMigrationPlanningError("MIGRATION_FILE_LAYOUT_INVALID")

    def _owned_file_rows(
        self,
        rows: list[tuple[object, object]] | tuple[tuple[object, object], ...],
        source_owner_id: str,
        namespace: str,
    ) -> set[str]:
        result: set[str] = set()
        for name, owner in rows:
            if not isinstance(owner, str) or not owner:
                raise OwnerMigrationPlanningError(
                    "MIGRATION_OWNER_RELATIONSHIP_UNRESOLVED"
                )
            if owner == source_owner_id:
                result.add(f"{namespace}:{name}")
        return result

    def _exam_file_references(
        self, connection: sqlite3.Connection, source_owner_id: str
    ) -> set[str]:
        owners: dict[tuple[str, str], set[str]] = {}
        for table in ("exam_papers", "exam_paper_revisions"):
            if not self._table_exists(connection, table):
                continue
            rows = connection.execute(
                f'SELECT owner_id, exam_paper_id, raw_json FROM "{table}"'
            ).fetchall()
            for owner, paper_id, raw_json in rows:
                if not isinstance(owner, str) or not owner:
                    raise OwnerMigrationPlanningError(
                        "MIGRATION_OWNER_RELATIONSHIP_UNRESOLVED"
                    )
                try:
                    payload = json.loads(str(raw_json))
                    items = payload["items"]
                    if not isinstance(items, list):
                        raise TypeError
                    for item in items:
                        question = item.get("question", {})
                        images = question.get("images", [])
                        if not isinstance(images, list):
                            raise TypeError
                        for image in images:
                            asset_id = image["asset_id"]
                            if not isinstance(asset_id, str) or not asset_id:
                                raise TypeError
                            owners.setdefault(
                                (str(paper_id), asset_id), set()
                            ).add(owner)
                except (KeyError, TypeError, json.JSONDecodeError) as error:
                    raise OwnerMigrationPlanningError(
                        "MIGRATION_FILE_EVIDENCE_MISMATCH"
                    ) from error
        if any(len(values) != 1 for values in owners.values()):
            raise OwnerMigrationPlanningError("MIGRATION_OWNER_RELATIONSHIP_UNRESOLVED")
        return {
            f"paper:{paper_id}:{asset_id}"
            for (paper_id, asset_id), values in owners.items()
            if source_owner_id in values
        }

    def _require_ready_evidence(
        self,
        inventory: OwnerDataInventoryReport,
        files: OwnerFileReconciliationReport,
    ) -> None:
        if not files.migration_ready:
            raise OwnerMigrationPlanningError("MIGRATION_FILE_RECONCILIATION_BLOCKED")
        file_stores = {item.store_id: item for item in files.stores}
        for store in inventory.stores:
            if store.status != "blocked":
                continue
            if (
                store.kind == "directory"
                and store.issues
                == ("INDIRECT_FILE_OWNERSHIP_REQUIRES_RECONCILIATION",)
                and store.store_id in file_stores
                and file_stores[store.store_id].migration_ready
            ):
                continue
            raise OwnerMigrationPlanningError("MIGRATION_INVENTORY_BLOCKED")

    @staticmethod
    def _require_closed_object_graph(
        tables: tuple[OwnerMigrationTablePlan, ...],
    ) -> None:
        known = {
            item.object_digest
            for table in tables
            for item in table.objects
        }
        dependencies = {
            dependency
            for table in tables
            for item in table.objects
            for dependency in item.dependency_digests
        }
        if not dependencies.issubset(known):
            raise OwnerMigrationPlanningError("MIGRATION_DEPENDENCY_NOT_PLANNED")

    def _validate_catalog(self) -> None:
        sqlite_specs = {
            spec.store_id: spec
            for spec in self._data_specs
            if isinstance(spec, OwnerSqliteStoreSpec)
        }
        expected = {
            (store.store_id, table.table_name)
            for store in sqlite_specs.values()
            for table in store.tables
            if table.ownership != "legacy_unowned"
        }
        actual = {(spec.store_id, spec.table_name) for spec in self._query_specs}
        if expected != actual or len(actual) != len(self._query_specs):
            raise OwnerMigrationPlanningError("MIGRATION_PLAN_CATALOG_INVALID")
        ownership = {
            (store.store_id, table.table_name): table.ownership
            for store in sqlite_specs.values()
            for table in store.tables
        }
        seen: set[tuple[str, str]] = set()
        for spec in self._query_specs:
            if (
                spec.store_id not in sqlite_specs
                or not self._SAFE_IDENTIFIER.fullmatch(spec.table_name)
                or not spec.key_columns
                or any(
                    not self._SAFE_IDENTIFIER.fullmatch(column)
                    for column in spec.key_columns
                )
                or spec.owner_columns < 1
                or not spec.query.lstrip().upper().startswith("SELECT ")
                or ";" in spec.query
                or ownership[(spec.store_id, spec.table_name)] != spec.ownership
            ):
                raise OwnerMigrationPlanningError("MIGRATION_PLAN_CATALOG_INVALID")
            for dependency in spec.dependencies:
                if (
                    not self._SAFE_IDENTIFIER.fullmatch(dependency.table_name)
                    or not dependency.key_columns
                    or any(
                        not self._SAFE_IDENTIFIER.fullmatch(column)
                        for column in dependency.key_columns
                    )
                    or (spec.store_id, dependency.table_name) not in seen
                ):
                    raise OwnerMigrationPlanningError(
                        "MIGRATION_PLAN_CATALOG_INVALID"
                    )
            seen.add((spec.store_id, spec.table_name))
        directory_ids = {
            spec.store_id
            for spec in self._data_specs
            if isinstance(spec, OwnerDirectoryStoreSpec)
        }
        if {spec.store_id for spec in self._file_specs} != directory_ids:
            raise OwnerMigrationPlanningError("MIGRATION_PLAN_CATALOG_INVALID")

    def _validate_request(
        self,
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
        inventory_fingerprint: str,
        file_fingerprint: str,
    ) -> None:
        values = (source_owner_id, target_owner_id, target_tenant_id)
        if any(not value or len(value) > 120 for value in values):
            raise OwnerMigrationPlanningError("MIGRATION_BINDING_INVALID")
        if source_owner_id == target_owner_id:
            raise OwnerMigrationPlanningError("MIGRATION_BINDING_UNCHANGED")
        if not self._FINGERPRINT.fullmatch(
            inventory_fingerprint
        ) or not self._FINGERPRINT.fullmatch(file_fingerprint):
            raise OwnerMigrationPlanningError("MIGRATION_EVIDENCE_INVALID")

    @staticmethod
    def _match_evidence(
        inventory: str,
        files: str,
        expected_inventory: str,
        expected_files: str,
    ) -> None:
        if inventory != expected_inventory or files != expected_files:
            raise OwnerMigrationPlanningError("MIGRATION_EVIDENCE_CHANGED")

    @classmethod
    def _object_digest(
        cls,
        binding: tuple[str, str, str],
        store_id: str,
        table_name: str,
        key: tuple[object, ...],
    ) -> str:
        return owner_object_digest(binding, store_id, table_name, key)

    @classmethod
    def _record_fingerprint(
        cls,
        connection: sqlite3.Connection,
        binding: tuple[str, str, str],
        spec: OwnerMigrationQuerySpec,
        key: tuple[object, ...],
    ) -> str:
        where = " AND ".join(
            f'"{column}" = ?' for column in spec.key_columns
        )
        rows = connection.execute(
            f'SELECT * FROM "{spec.table_name}" WHERE {where}', key
        ).fetchall()
        if len(rows) != 1:
            raise OwnerMigrationPlanningError("MIGRATION_OBJECT_NOT_UNIQUE")
        columns = tuple(
            str(row[1])
            for row in connection.execute(
                f'PRAGMA table_info("{spec.table_name}")'
            )
        )
        try:
            return source_record_fingerprint(
                binding,
                spec.store_id,
                spec.table_name,
                columns,
                tuple(rows[0]),
            )
        except OwnerMigrationFingerprintError as error:
            raise OwnerMigrationPlanningError(
                "MIGRATION_RECORD_VALUE_INVALID"
            ) from error

    @staticmethod
    def _canonical_sqlite_value(value: object) -> object:
        try:
            return canonical_sqlite_value(value)
        except OwnerMigrationFingerprintError as error:
            raise OwnerMigrationPlanningError(
                "MIGRATION_RECORD_VALUE_INVALID"
            ) from error

    @staticmethod
    def _validate_key(key: tuple[object, ...]) -> None:
        if not key or any(
            value is None
            or not isinstance(value, (str, int, float))
            or (isinstance(value, float) and not math.isfinite(value))
            for value in key
        ):
            raise OwnerMigrationPlanningError("MIGRATION_OBJECT_KEY_INVALID")

    @staticmethod
    def _digest(value: object) -> str:
        return canonical_digest(value)

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        encoded = quote(path.resolve().as_posix(), safe="/:")
        connection = sqlite3.connect(f"file:{encoded}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only = ON")
        return connection

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone() is not None
