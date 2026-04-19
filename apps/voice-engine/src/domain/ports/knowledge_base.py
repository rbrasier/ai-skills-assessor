"""``IKnowledgeBase`` port — RAG retrieval surface (stub for Phase 1).

The full contract is defined in the RAG phase; this stub exists so adapters
and orchestration code can already depend on a stable interface name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.models.skill import SkillDefinition


class IKnowledgeBase(ABC):
    @abstractmethod
    async def search_skills(
        self,
        query: str,
        framework: str = "SFIA",
        limit: int = 5,
    ) -> list[SkillDefinition]:
        """Return the top ``limit`` skill definitions relevant to ``query``."""
        ...
