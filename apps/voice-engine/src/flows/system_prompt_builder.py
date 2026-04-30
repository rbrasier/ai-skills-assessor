"""Static cached system prompt builder.

Fetches framework rubric and Generic Attributes from the database once at
call initialisation. The resulting string is passed to
``SfiaFlowController.__init__(system_prompt=...)`` and used as
``role_message`` in every node config so Claude caches it across turns.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SystemPromptBuilder:
    """Builds the static system prompt for caching by Claude."""

    def __init__(self, db_pool: Any) -> None:
        self._db_pool = db_pool

    async def build_cached_system_prompt(
        self,
        framework_type: str = "sfia-9",
        framework_version: str = "9.0",
    ) -> str:
        """Fetch rubric + Generic Attributes and return the full system prompt.

        Raises ``ValueError`` if the framework record is not found (i.e. the
        SFIA 9 data has not been seeded yet).
        """
        framework = await self._fetch_framework(framework_type, framework_version)
        if not framework:
            raise ValueError(
                f"Framework '{framework_type}' v{framework_version} not found. "
                "Run create_framework.py to seed the frameworks table."
            )

        rubric = framework["rubric"]
        attributes_text = await self._build_attributes_section(framework["id"])

        return (
            "You are Noa, a warm and professional AI skills assessor from Resonant. "
            "You conduct structured SFIA-based skills assessments over the phone.\n\n"
            "## Assessment Methodology\n\n"
            "Your role is to:\n"
            "1. Conduct a natural, conversational interview (no jargon, no SFIA codes mentioned to the candidate)\n"
            "2. Listen for evidence of skills and responsibility levels\n"
            "3. Probe deeper when evidence suggests higher levels of autonomy, influence, or complexity\n"
            "4. Record claims and map them to framework skills\n\n"
            "Keep your language conversational, concise, and encouraging.\n\n"
            "## Assessor Behavioral Scoring Rubric\n\n"
            f"{rubric}\n\n"
            "## Framework Generic Attributes Reference\n\n"
            "Use these definitions when scoring responsibility levels (1-7):\n\n"
            f"{attributes_text}\n\n"
            "## Instructions for Dynamic RAG Context\n\n"
            "When skill definitions are injected into the conversation, they will appear as:\n"
            ">>> SKILL DEFINITIONS START\n"
            "[Skill definitions and examples]\n"
            ">>> SKILL DEFINITIONS END\n\n"
            "Use these definitions to ask level-appropriate probing questions and validate "
            "evidence against framework definitions. Never quote framework codes to the candidate."
        )

    async def _fetch_framework(
        self, framework_type: str, framework_version: str
    ) -> dict | None:
        async with self._db_pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT id, type, version, name, rubric "
                "FROM frameworks WHERE type = $1 AND version = $2",
                framework_type,
                framework_version,
            )

    async def _build_attributes_section(self, framework_id: str) -> str:
        async with self._db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT attribute, level, description "
                "FROM framework_attributes "
                "WHERE framework_id = $1 "
                "ORDER BY attribute, level",
                framework_id,
            )

        attributes: dict[str, list[tuple[int, str]]] = {}
        for row in rows:
            attr = row["attribute"]
            if attr not in attributes:
                attributes[attr] = []
            attributes[attr].append((row["level"], row["description"]))

        sections = []
        for attr in sorted(attributes):
            section = f"### {attr}\n"
            for level, description in attributes[attr]:
                section += f"Level {level}: {description}\n"
            sections.append(section)

        return "\n".join(sections)
