from __future__ import annotations

import base64
import json
import math
import re
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn
from urllib.parse import quote

from app.modules.tenant_migration.fingerprints import (
    canonical_digest,
    owner_object_digest,
    source_record_fingerprint,
    target_binding_fingerprint,
)
from app.modules.tenant_migration.inventory import (
    OwnerSqliteStoreSpec,
    OwnerStoreSpec,
)
from app.modules.tenant_migration.planning import OwnerMigrationQuerySpec
from app.modules.tenant_migration.schemas import (
    OwnerMigrationPlanReport,
    OwnerMigrationTablePlan,
)


class OwnerMigrationMaterializationError(ValueError):
    """A planned source object cannot be materialized without ambiguity."""


Connect = Callable[[Path], sqlite3.Connection]


@dataclass(frozen=True, repr=False)
class MaterializedMigrationObject:
    sequence: int
    store_id: str
    table_name: str
    object_digest: str
    source_record_fingerprint: str
    dependency_digests: tuple[str, ...]
    payload_json: str = field(repr=False)


@dataclass(frozen=True, repr=False)
class OwnerMigrationObjectBatch:
    plan_fingerprint: str
    target_binding_fingerprint: str
    object_count: int
    objects: tuple[MaterializedMigrationObject, ...] = field(repr=False)


class OwnerMigrationObjectMaterializer:
    """Re-read planned SQLite rows into private, target-bound payloads."""

    _SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,79}$")

    def __init__(
        self,
        data_specs: tuple[OwnerStoreSpec, ...],
        query_specs: tuple[OwnerMigrationQuerySpec, ...],
        *,
        connect: Connect | None = None,
    ) -> None:
        self._stores = {
            spec.store_id: spec
            for spec in data_specs
            if isinstance(spec, OwnerSqliteStoreSpec)
        }
        self._query_specs = query_specs
        self._connect = connect or self._readonly_connect
        self._validate_catalog()

    def materialize(
        self,
        *,
        plan: OwnerMigrationPlanReport,
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
    ) -> OwnerMigrationObjectBatch:
        self._validate_binding(
            source_owner_id,
            target_owner_id,
            target_tenant_id,
        )
        expected_target = target_binding_fingerprint(
            target_owner_id,
            target_tenant_id,
        )
        if not secrets.compare_digest(
            plan.target_binding_fingerprint,
            expected_target,
        ):
            raise OwnerMigrationMaterializationError(
                "MIGRATION_MATERIALIZATION_TARGET_CHANGED"
            )
        self._validate_plan(plan)

        binding = (source_owner_id, target_owner_id, target_tenant_id)
        planned_tables = {
            (table.store_id, table.table_name): table for table in plan.tables
        }
        if len(planned_tables) != len(plan.tables):
            raise OwnerMigrationMaterializationError(
                "MIGRATION_MATERIALIZATION_PLAN_INVALID"
            )
        objects: list[MaterializedMigrationObject] = []
        table_sequence = 1
        object_sequence = 1
        try:
            for spec in self._query_specs:
                store = self._stores[spec.store_id]
                if not store.path.exists():
                    continue
                with self._connect(store.path) as connection:
                    if not self._table_exists(connection, spec.table_name):
                        continue
                    planned = planned_tables.pop(
                        (spec.store_id, spec.table_name),
                        None,
                    )
                    if (
                        planned is None
                        or planned.sequence != table_sequence
                        or planned.ownership != spec.ownership
                    ):
                        self._source_changed()
                    current = self._materialize_table(
                        connection=connection,
                        spec=spec,
                        planned=planned,
                        binding=binding,
                        source_owner_id=source_owner_id,
                        target_owner_id=target_owner_id,
                        target_tenant_id=target_tenant_id,
                        first_sequence=object_sequence,
                    )
                objects.extend(current)
                object_sequence += len(current)
                table_sequence += 1
        except OwnerMigrationMaterializationError:
            raise
        except Exception as error:
            raise OwnerMigrationMaterializationError(
                "MIGRATION_OBJECT_MATERIALIZATION_FAILED"
            ) from error

        if planned_tables or len(objects) != plan.object_count:
            self._source_changed()
        return OwnerMigrationObjectBatch(
            plan_fingerprint=plan.plan_fingerprint,
            target_binding_fingerprint=expected_target,
            object_count=len(objects),
            objects=tuple(objects),
        )

    def _materialize_table(
        self,
        *,
        connection: sqlite3.Connection,
        spec: OwnerMigrationQuerySpec,
        planned: OwnerMigrationTablePlan,
        binding: tuple[str, str, str],
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
        first_sequence: int,
    ) -> tuple[MaterializedMigrationObject, ...]:
        expected_width = len(spec.key_columns) + sum(
            len(item.key_columns) for item in spec.dependencies
        ) + spec.owner_columns
        rows = connection.execute(spec.query).fetchall()
        current: dict[str, tuple[tuple[object, ...], tuple[str, ...]]] = {}
        for row in rows:
            if len(row) != expected_width:
                self._source_changed()
            owners = tuple(row[-spec.owner_columns :])
            if (
                len(owners) != spec.owner_columns
                or any(not isinstance(owner, str) or not owner for owner in owners)
                or len(set(owners)) != 1
            ):
                self._source_changed()
            cursor = len(spec.key_columns)
            key = tuple(row[:cursor])
            self._validate_key(key)
            dependency_digests: list[str] = []
            for dependency in spec.dependencies:
                width = len(dependency.key_columns)
                values = tuple(row[cursor : cursor + width])
                self._validate_key(values)
                dependency_digests.append(
                    owner_object_digest(
                        binding,
                        spec.store_id,
                        dependency.table_name,
                        values,
                    )
                )
                cursor += width
            if owners[0] != source_owner_id:
                continue
            digest = owner_object_digest(
                binding,
                spec.store_id,
                spec.table_name,
                key,
            )
            if digest in current:
                self._source_changed()
            current[digest] = (key, tuple(dependency_digests))

        planned_objects = {item.object_digest: item for item in planned.objects}
        if (
            len(planned_objects) != len(planned.objects)
            or set(current) != set(planned_objects)
            or planned.object_count != len(current)
        ):
            self._source_changed()
        if planned.object_set_fingerprint != canonical_digest(
            [item.model_dump(mode="json") for item in planned.objects]
        ):
            self._source_changed()

        result: list[MaterializedMigrationObject] = []
        for offset, digest in enumerate(sorted(current)):
            key, dependencies = current[digest]
            expected = planned_objects[digest]
            if expected.dependency_digests != dependencies:
                self._source_changed()
            columns, record = self._read_record(connection, spec, key)
            fingerprint = source_record_fingerprint(
                binding,
                spec.store_id,
                spec.table_name,
                columns,
                record,
            )
            if not secrets.compare_digest(
                expected.source_record_fingerprint,
                fingerprint,
            ):
                self._source_changed()
            payload = self._payload_json(
                columns,
                record,
                target_owner_id,
                target_tenant_id,
            )
            result.append(
                MaterializedMigrationObject(
                    sequence=first_sequence + offset,
                    store_id=spec.store_id,
                    table_name=spec.table_name,
                    object_digest=digest,
                    source_record_fingerprint=fingerprint,
                    dependency_digests=dependencies,
                    payload_json=payload,
                )
            )
        return tuple(result)

    def _validate_plan(self, plan: OwnerMigrationPlanReport) -> None:
        canonical = {
            "schema_version": plan.schema_version,
            "source_inventory_fingerprint": plan.source_inventory_fingerprint,
            "source_file_reconciliation_fingerprint": (
                plan.source_file_reconciliation_fingerprint
            ),
            "target_binding_fingerprint": plan.target_binding_fingerprint,
            "tables": [table.model_dump(mode="json") for table in plan.tables],
            "files": [item.model_dump(mode="json") for item in plan.files],
        }
        if not secrets.compare_digest(
            plan.plan_fingerprint,
            canonical_digest(canonical),
        ):
            raise OwnerMigrationMaterializationError(
                "MIGRATION_MATERIALIZATION_PLAN_INVALID"
            )
        if plan.object_count != sum(table.object_count for table in plan.tables):
            raise OwnerMigrationMaterializationError(
                "MIGRATION_MATERIALIZATION_PLAN_INVALID"
            )
        if plan.file_count != sum(item.object_count for item in plan.files):
            raise OwnerMigrationMaterializationError(
                "MIGRATION_MATERIALIZATION_PLAN_INVALID"
            )

    def _validate_catalog(self) -> None:
        known_tables = {
            (store.store_id, table.table_name): table.ownership
            for store in self._stores.values()
            for table in store.tables
            if table.ownership != "legacy_unowned"
        }
        actual = {(spec.store_id, spec.table_name) for spec in self._query_specs}
        if actual != set(known_tables) or len(actual) != len(self._query_specs):
            raise OwnerMigrationMaterializationError(
                "MIGRATION_MATERIALIZATION_CATALOG_INVALID"
            )
        seen: set[tuple[str, str]] = set()
        for spec in self._query_specs:
            if (
                spec.store_id not in self._stores
                or not self._SAFE_IDENTIFIER.fullmatch(spec.table_name)
                or not spec.key_columns
                or any(
                    not self._SAFE_IDENTIFIER.fullmatch(column)
                    for column in spec.key_columns
                )
                or spec.owner_columns < 1
                or not spec.query.lstrip().upper().startswith("SELECT ")
                or ";" in spec.query
                or known_tables.get((spec.store_id, spec.table_name))
                != spec.ownership
            ):
                raise OwnerMigrationMaterializationError(
                    "MIGRATION_MATERIALIZATION_CATALOG_INVALID"
                )
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
                    raise OwnerMigrationMaterializationError(
                        "MIGRATION_MATERIALIZATION_CATALOG_INVALID"
                    )
            seen.add((spec.store_id, spec.table_name))

    @staticmethod
    def _validate_binding(
        source_owner_id: str,
        target_owner_id: str,
        target_tenant_id: str,
    ) -> None:
        values = (source_owner_id, target_owner_id, target_tenant_id)
        if (
            any(not value or len(value) > 120 for value in values)
            or source_owner_id == target_owner_id
        ):
            raise OwnerMigrationMaterializationError(
                "MIGRATION_MATERIALIZATION_BINDING_INVALID"
            )

    @staticmethod
    def _validate_key(key: tuple[object, ...]) -> None:
        if not key or any(
            value is None
            or not isinstance(value, (str, int, float))
            or (isinstance(value, float) and not math.isfinite(value))
            for value in key
        ):
            OwnerMigrationObjectMaterializer._source_changed()

    @classmethod
    def _read_record(
        cls,
        connection: sqlite3.Connection,
        spec: OwnerMigrationQuerySpec,
        key: tuple[object, ...],
    ) -> tuple[tuple[str, ...], tuple[object, ...]]:
        where = " AND ".join(f'"{column}" = ?' for column in spec.key_columns)
        rows = connection.execute(
            f'SELECT * FROM "{spec.table_name}" WHERE {where}',
            key,
        ).fetchall()
        columns = tuple(
            str(row[1])
            for row in connection.execute(
                f'PRAGMA table_info("{spec.table_name}")'
            )
        )
        if len(rows) != 1 or len(columns) != len(rows[0]):
            cls._source_changed()
        return columns, tuple(rows[0])

    @staticmethod
    def _payload_json(
        columns: tuple[str, ...],
        record: tuple[object, ...],
        target_owner_id: str,
        target_tenant_id: str,
    ) -> str:
        values: list[object] = []
        for column, value in zip(columns, record, strict=True):
            if column == "owner_id":
                value = target_owner_id
            elif column == "tenant_id":
                value = target_tenant_id
            values.append(OwnerMigrationObjectMaterializer._payload_value(value))
        return json.dumps(
            {"columns": columns, "values": values},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

    @staticmethod
    def _payload_value(value: object) -> object:
        if isinstance(value, bytes):
            return {
                "base64": base64.b64encode(value).decode("ascii"),
                "encoding": "base64",
            }
        if value is None or isinstance(value, (str, int)):
            return value
        if isinstance(value, float) and math.isfinite(value):
            return value
        raise OwnerMigrationMaterializationError(
            "MIGRATION_OBJECT_MATERIALIZATION_FAILED"
        )

    @staticmethod
    def _source_changed() -> NoReturn:
        raise OwnerMigrationMaterializationError(
            "MIGRATION_MATERIALIZATION_SOURCE_CHANGED"
        )

    @staticmethod
    def _readonly_connect(path: Path) -> sqlite3.Connection:
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
