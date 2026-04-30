"""pgvector-backed knowledge base adapter (Phase 5 full implementation).

Replaces the Phase 1 stub that raised ``NotImplementedError``.
"""

from __future__ import annotations

import logging
from typing import Any

from src.domain.ports.embedding_service import IEmbeddingService
from src.domain.ports.knowledge_base import IKnowledgeBase, SkillDefinition

logger = logging.getLogger(__name__)


class PgVectorKnowledgeBase(IKnowledgeBase):
    """Adapter for pgvector-based skill retrieval from PostgreSQL.

    Args:
        db_pool: asyncpg connection pool.
        embedder: Embedding service for ``query()`` semantic search.
                  Optional — ``query_by_skill_code()`` does not require it.
    """

    def __init__(self, db_pool: Any, embedder: IEmbeddingService | None = None) -> None:
        self._db_pool = db_pool
        self._embedder = embedder

    async def query(
        self,
        text: str,
        framework_type: str = "sfia-9",
        top_k: int = 5,
        level_filter: int | None = None,
        skill_codes: list[str] | None = None,
    ) -> list[SkillDefinition]:
        """Semantic similarity search against pgvector embeddings."""
        if self._embedder is None:
            raise RuntimeError(
                "PgVectorKnowledgeBase.query() requires an embedder. "
                "Pass an IEmbeddingService at construction time."
            )

        embedding = await self._embedder.embed(text)

        conditions = ["f.type = $2"]
        params: list[object] = [embedding, framework_type]
        param_idx = 3

        if level_filter is not None:
            conditions.append(f"fsl.level = ${param_idx}")
            params.append(level_filter)
            param_idx += 1

        if skill_codes:
            conditions.append(f"fs.skill_code = ANY(${param_idx}::text[])")
            params.append(skill_codes)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT fs.skill_code, fs.skill_name, fs.category, fs.subcategory,
                   fsl.level, fsl.content, f.type AS framework_type,
                   1 - (fsl.embedding <=> $1::vector) AS similarity
            FROM framework_skill_levels fsl
            JOIN framework_skills fs ON fs.id = fsl.framework_skill_id
            JOIN frameworks f ON f.id = fs.framework_id
            WHERE {where_clause}
            ORDER BY fsl.embedding <=> $1::vector
            LIMIT {top_k}
        """

        async with self._db_pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [
            SkillDefinition(
                skill_code=row["skill_code"],
                skill_name=row["skill_name"],
                category=row["category"],
                subcategory=row["subcategory"],
                level=row["level"],
                content=row["content"],
                similarity=row["similarity"],
                framework_type=row["framework_type"],
            )
            for row in rows
        ]

    async def query_by_skill_code(
        self,
        skill_code: str,
        framework_type: str = "sfia-9",
    ) -> list[SkillDefinition]:
        """Direct lookup: all levels for a skill code (no vector search)."""
        sql = """
            SELECT fs.skill_code, fs.skill_name, fs.category, fs.subcategory,
                   fsl.level, fsl.content, f.type AS framework_type
            FROM framework_skill_levels fsl
            JOIN framework_skills fs ON fs.id = fsl.framework_skill_id
            JOIN frameworks f ON f.id = fs.framework_id
            WHERE f.type = $1 AND fs.skill_code = $2
            ORDER BY fsl.level ASC NULLS LAST
        """

        async with self._db_pool.acquire() as conn:
            rows = await conn.fetch(sql, framework_type, skill_code)

        return [
            SkillDefinition(
                skill_code=row["skill_code"],
                skill_name=row["skill_name"],
                category=row["category"],
                subcategory=row["subcategory"],
                level=row["level"],
                content=row["content"],
                similarity=None,
                framework_type=row["framework_type"],
            )
            for row in rows
        ]
