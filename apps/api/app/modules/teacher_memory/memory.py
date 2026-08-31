from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.modules.teacher_memory.schemas import (
    TeacherMemoryCommand,
    TeacherMemoryProfile,
    TeacherPreference,
    TeacherPreferenceKey,
    TeacherPreferenceSource,
    TeacherPreferenceValue,
)


PREFERENCE_LABELS: dict[str, str] = {
    "default_grade": "默认年级",
    "default_difficulty": "默认难度",
    "default_lesson_minutes": "默认课时",
    "solution_detail_level": "解析详略",
    "preferred_question_types": "常用题型",
}
GRADES = {"高一", "高二", "高三", "高中通用"}
DETAIL_LEVELS = {"concise", "standard", "detailed"}
QUESTION_TYPES = {"single_choice", "multiple_choice", "fill_blank", "open_response"}


class TeacherMemoryError(ValueError):
    pass


class TeacherMemoryConflict(TeacherMemoryError):
    pass


class TeacherMemory:
    """Owner-scoped structured preference memory.

    Callers provide identity and commands; persistence, provenance and validation
    remain private to this module.
    """

    def __init__(self, *, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def profile(self, *, owner_id: str) -> TeacherMemoryProfile:
        with self._connect() as connection:
            return self._profile(connection, owner_id=owner_id)

    def apply(
        self,
        command: TeacherMemoryCommand,
        *,
        owner_id: str,
    ) -> TeacherMemoryProfile:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._profile(connection, owner_id=owner_id)
            if command.expected_version is not None and command.expected_version != current.version:
                raise TeacherMemoryConflict("教师偏好已在其他页面更新，请刷新后重试。")

            changed = False
            now = datetime.now(timezone.utc).isoformat()
            if command.operation == "upsert":
                if command.key is None or command.value is None:
                    raise TeacherMemoryError("保存偏好时必须提供偏好项和值。")
                value = self._validate_value(command.key, command.value)
                connection.execute(
                    """INSERT INTO m11_teacher_preferences
                       (owner_id, preference_key, value_json, source_kind, confidence, updated_at)
                       VALUES (?, ?, ?, 'teacher_explicit', 1.0, ?)
                       ON CONFLICT(owner_id, preference_key) DO UPDATE SET
                         value_json = excluded.value_json,
                         source_kind = 'teacher_explicit',
                         confidence = 1.0,
                         updated_at = excluded.updated_at""",
                    (owner_id, command.key, json.dumps(value, ensure_ascii=False), now),
                )
                changed = True
            elif command.operation == "remove":
                if command.key is None:
                    raise TeacherMemoryError("删除偏好时必须提供偏好项。")
                changed = connection.execute(
                    "DELETE FROM m11_teacher_preferences WHERE owner_id = ? AND preference_key = ?",
                    (owner_id, command.key),
                ).rowcount > 0
            else:
                if command.enabled is None:
                    raise TeacherMemoryError("设置自动学习时必须提供开关状态。")
                changed = command.enabled != current.auto_learning_enabled

            if changed:
                next_version = current.version + 1
                auto_learning = (
                    command.enabled
                    if command.operation == "set_auto_learning"
                    else current.auto_learning_enabled
                )
                connection.execute(
                    """INSERT INTO m11_teacher_memory_profiles
                       (owner_id, version, auto_learning_enabled, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(owner_id) DO UPDATE SET
                         version = excluded.version,
                         auto_learning_enabled = excluded.auto_learning_enabled,
                         updated_at = excluded.updated_at""",
                    (owner_id, next_version, int(bool(auto_learning)), now, now),
                )
            return self._profile(connection, owner_id=owner_id)

    def _validate_value(
        self,
        key: TeacherPreferenceKey,
        value: TeacherPreferenceValue,
    ) -> TeacherPreferenceValue:
        if key == "default_grade":
            if not isinstance(value, str) or value not in GRADES:
                raise TeacherMemoryError("默认年级必须是高一、高二、高三或高中通用。")
            return value
        if key == "default_difficulty":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
                raise TeacherMemoryError("默认难度必须是 1 至 5 的整数。")
            return value
        if key == "default_lesson_minutes":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 300:
                raise TeacherMemoryError("默认课时必须是 1 至 300 分钟。")
            return value
        if key == "solution_detail_level":
            if not isinstance(value, str) or value not in DETAIL_LEVELS:
                raise TeacherMemoryError("解析详略必须是简洁、标准或详细。")
            return value
        if key == "preferred_question_types":
            if (
                not isinstance(value, list)
                or not value
                or len(value) > len(QUESTION_TYPES)
                or any(not isinstance(item, str) or item not in QUESTION_TYPES for item in value)
            ):
                raise TeacherMemoryError("常用题型必须从受支持题型中选择。")
            return list(dict.fromkeys(value))
        raise TeacherMemoryError("不支持的教师偏好项。")

    def _profile(self, connection: sqlite3.Connection, *, owner_id: str) -> TeacherMemoryProfile:
        profile_row = connection.execute(
            "SELECT version, auto_learning_enabled FROM m11_teacher_memory_profiles WHERE owner_id = ?",
            (owner_id,),
        ).fetchone()
        rows = connection.execute(
            """SELECT preference_key, value_json, source_kind, confidence, updated_at
               FROM m11_teacher_preferences
               WHERE owner_id = ? ORDER BY preference_key""",
            (owner_id,),
        ).fetchall()
        preferences = [
            TeacherPreference(
                key=row["preference_key"],
                label=PREFERENCE_LABELS[row["preference_key"]],
                value=json.loads(row["value_json"]),
                source=TeacherPreferenceSource(
                    kind=row["source_kind"],
                    confidence=float(row["confidence"]),
                ),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
        return TeacherMemoryProfile(
            version=int(profile_row["version"]) if profile_row else 0,
            auto_learning_enabled=bool(profile_row["auto_learning_enabled"]) if profile_row else False,
            preferences=preferences,
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS m11_teacher_memory_profiles (
                    owner_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    auto_learning_enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS m11_teacher_preferences (
                    owner_id TEXT NOT NULL,
                    preference_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (owner_id, preference_key)
                );
                """
            )
