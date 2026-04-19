"""pgvector-backed knowledge base adapter — stub for Phase 1."""

from __future__ import annotations

from src.domain.models.skill import SkillDefinition
from src.domain.ports.knowledge_base import IKnowledgeBase


class PgVectorKnowledgeBase(IKnowledgeBase):
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def search_skills(
        self,
        query: str,
        framework: str = "SFIA",
        limit: int = 5,
    ) -> list[SkillDefinition]:
        raise NotImplementedError(
            "PgVectorKnowledgeBase.search_skills is implemented in the RAG phase",
        )
