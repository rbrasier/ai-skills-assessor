"""Ingest SFIA skills from Excel into ``framework_skills`` + ``framework_skill_levels``.

This script UPDATES the embeddings in an existing database. For a fresh database,
apply the SQL migration first:
  packages/database/prisma/migrations/v0_9_0_local_embeddings_sfia_data/migration.sql

The migration seeds all 147 skills with pre-computed embeddings so this script
is only needed to re-embed with a different model (e.g. upgrading from LSA to
sentence-transformers once internet access is available).

Usage::

    # Local embedder — no API key or internet required:
    python -m src.scripts.ingest_sfia_skills \\
      --excel docs/development/contracts/sfia-9.xlsx \\
      --embedder sentence-transformers    # or: lsa

    # OpenAI (legacy, requires OPENAI_API_KEY):
    python -m src.scripts.ingest_sfia_skills \\
      --excel docs/development/contracts/sfia-9.xlsx \\
      --embedder openai

Excel column layout (0-indexed):
  0:    Row #
  1-7:  Level indicators (non-null = skill available at that level)
  8:    Skill code   ← was incorrectly read as col 0 in earlier versions
  9:    URL (ignored)
  10:   Skill name
  11:   Category
  12:   Subcategory
  13:   Overall description
  14:   Guidance notes
  15-21: Level 1-7 descriptions
"""

from __future__ import annotations

import argparse
import asyncio
import os


async def ingest_sfia_skills(
    *,
    excel_path: str,
    framework_type: str,
    framework_version: str,
    database_url: str,
    embedder_name: str,
    openai_api_key: str = "",
    lsa_model_path: str = "",
) -> None:
    import asyncpg
    import openpyxl

    from src.domain.ports.embedding_service import IEmbeddingService

    embedder: IEmbeddingService
    if embedder_name == "openai":
        from src.adapters.openai_embedder import OpenAIEmbeddingService

        if not openai_api_key:
            raise SystemExit("--openai-api-key (or $OPENAI_API_KEY) is required for openai embedder")
        embedder = OpenAIEmbeddingService(api_key=openai_api_key)
    elif embedder_name == "sentence-transformers":
        from src.adapters.sentence_transformers_embedder import SentenceTransformersEmbeddingService

        embedder = SentenceTransformersEmbeddingService()
    elif embedder_name == "lsa":
        from src.adapters.sklearn_lsa_embedder import SklearnLsaEmbeddingService

        kwargs = {"model_path": lsa_model_path} if lsa_model_path else {}
        embedder = SklearnLsaEmbeddingService(**kwargs)
    else:
        raise SystemExit(f"Unknown embedder: {embedder_name!r}")

    pool = await asyncpg.create_pool(database_url)
    try:
        async with pool.acquire() as conn:
            framework_id = await conn.fetchval(
                "SELECT id FROM frameworks WHERE type = $1 AND version = $2",
                framework_type,
                framework_version,
            )
            if not framework_id:
                raise SystemExit(
                    f"Framework '{framework_type}' v{framework_version} not found. "
                    "Apply the v0_9_0 migration or run create_framework.py first."
                )

        wb = openpyxl.load_workbook(excel_path, data_only=True)
        sheet = wb["Skills"]

        chunks_ingested = 0
        skills_upserted = 0
        failed = 0

        async with pool.acquire() as conn:
            for row in sheet.iter_rows(min_row=2, values_only=True):
                # Skill code is at index 8 (column I), not index 0.
                if not row[8]:
                    continue

                try:
                    skill_code = str(row[8]).strip()
                    skill_name = str(row[10] or "").strip()
                    category = str(row[11] or "").strip()
                    subcategory = str(row[12]).strip() if row[12] else None
                    overall_desc = str(row[13] or "").strip()
                    guidance = str(row[14]).strip() if row[14] else None
                    # Columns P-V are level 1-7 descriptions (indices 15-21)
                    level_descriptions = [
                        str(row[15 + i]).strip() if (15 + i) < len(row) and row[15 + i] else ""
                        for i in range(7)
                    ]

                    framework_skill_id = await conn.fetchval(
                        """
                        INSERT INTO framework_skills
                            (framework_id, skill_code, skill_name, category,
                             subcategory, description, guidance)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (framework_id, skill_code)
                        DO UPDATE SET
                            skill_name  = EXCLUDED.skill_name,
                            category    = EXCLUDED.category,
                            subcategory = EXCLUDED.subcategory,
                            description = EXCLUDED.description,
                            guidance    = EXCLUDED.guidance,
                            updated_at  = now()
                        RETURNING id
                        """,
                        framework_id,
                        skill_code,
                        skill_name,
                        category,
                        subcategory,
                        overall_desc,
                        guidance,
                    )
                    skills_upserted += 1

                    for level, level_desc in enumerate(level_descriptions, start=1):
                        if not level_desc:
                            continue

                        cat_str = f"{category} > {subcategory}" if subcategory else category
                        content = (
                            f"Framework: SFIA 9\n"
                            f"Skill: {skill_name} ({skill_code})\n"
                            f"Category: {cat_str}\n"
                            f"Level: {level}\n\n"
                            f"Overall Description:\n{overall_desc}\n\n"
                            f"Level {level} Description:\n{level_desc}"
                            + (f"\n\nGuidance:\n{guidance}" if guidance else "")
                        )

                        embedding = await embedder.embed(content)

                        await conn.execute(
                            """
                            INSERT INTO framework_skill_levels
                                (framework_skill_id, level, content, embedding)
                            VALUES ($1, $2, $3, $4)
                            ON CONFLICT (framework_skill_id, level)
                            DO UPDATE SET
                                content   = EXCLUDED.content,
                                embedding = EXCLUDED.embedding
                            """,
                            framework_skill_id,
                            level,
                            content,
                            str(embedding),
                        )
                        chunks_ingested += 1

                except Exception as exc:
                    print(f"  ERROR ingesting skill '{row[8]}': {exc}")
                    failed += 1

        print(
            f"Done. Skills upserted: {skills_upserted}, "
            f"level chunks ingested: {chunks_ingested}, "
            f"failed: {failed}"
        )
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-embed SFIA skills into framework_skills / framework_skill_levels"
    )
    parser.add_argument("--excel", required=True, help="Path to sfia-9.xlsx")
    parser.add_argument("--framework-type", default="sfia-9")
    parser.add_argument("--framework-version", default="9.0")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
    )
    parser.add_argument(
        "--embedder",
        choices=["sentence-transformers", "lsa", "openai"],
        default="sentence-transformers",
        help="Embedding backend to use (default: sentence-transformers)",
    )
    parser.add_argument(
        "--openai-api-key",
        default=os.environ.get("OPENAI_API_KEY", ""),
        help="[openai embedder only] OpenAI API key",
    )
    parser.add_argument(
        "--lsa-model-path",
        default="",
        help="[lsa embedder only] Path to sfia_lsa_model.joblib (uses default if empty)",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is not set")

    asyncio.run(
        ingest_sfia_skills(
            excel_path=args.excel,
            framework_type=args.framework_type,
            framework_version=args.framework_version,
            database_url=args.database_url,
            embedder_name=args.embedder,
            openai_api_key=args.openai_api_key,
            lsa_model_path=args.lsa_model_path,
        )
    )


if __name__ == "__main__":
    main()
