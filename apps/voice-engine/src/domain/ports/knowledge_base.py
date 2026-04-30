"""``IKnowledgeBase`` port — RAG retrieval surface (Phase 5 full contract).

Replaces the Phase 1 stub. ``SkillDefinition`` is defined here (not in
``domain/models/skill.py``) so adapters and the flow controller share the
same type without a cross-layer import.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SkillDefinition:
    skill_code: str
    skill_name: str
    category: str
    subcategory: str | None
    level: int | None
    content: str
    similarity: float | None  # relevance score 0-1; None for direct lookups
    framework_type: str


class IKnowledgeBase(ABC):
    @abstractmethod
    async def query(
        self,
        text: str,
        framework_type: str = "sfia-9",
        top_k: int = 5,
        level_filter: int | None = None,
        skill_codes: list[str] | None = None,
    ) -> list[SkillDefinition]:
        """Query the knowledge base for skill definitions relevant to ``text``.

        Args:
            text: Query text to embed and search on.
            framework_type: Which framework to search (default: sfia-9).
            top_k: Max results to return.
            level_filter: Restrict to a specific responsibility level (1-7).
            skill_codes: Restrict to specific skill codes for targeted probing.

        Returns:
            List of SkillDefinition ordered by relevance (highest first).
        """
        ...

    @abstractmethod
    async def query_by_skill_code(
        self,
        skill_code: str,
        framework_type: str = "sfia-9",
    ) -> list[SkillDefinition]:
        """Retrieve all levels for a specific skill (no vector search)."""
        ...
