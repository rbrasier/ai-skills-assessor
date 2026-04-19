"""Stub skill / framework models.

Only enough is defined here for the Phase 1 scaffold to typecheck. Full SFIA
modelling lands in the RAG / claim-extraction phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class SFIALevel(IntEnum):
    """SFIA 9 responsibility levels (1 = Follow … 7 = Set Strategy)."""

    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3
    LEVEL_4 = 4
    LEVEL_5 = 5
    LEVEL_6 = 6
    LEVEL_7 = 7


@dataclass(frozen=True)
class SkillDefinition:
    framework: str  # e.g. "SFIA"
    code: str       # e.g. "PROG"
    name: str
    level: SFIALevel
    description: str
