from __future__ import annotations

from typing import Literal


WorkbenchCapability = Literal[
    "search",
    "solve",
    "library",
    "authoring",
    "lesson",
    "paper",
    "teacher_memory",
]

ALL_WORKBENCH_CAPABILITIES: tuple[WorkbenchCapability, ...] = (
    "search",
    "solve",
    "library",
    "authoring",
    "lesson",
    "paper",
    "teacher_memory",
)
