"""Ingest SFIA skills from Excel into ``framework_skills`` + ``framework_skill_levels``.

Usage::

    python -m src.scripts.ingest_sfia_skills \\
      --excel docs/development/contracts/sfia-9.xlsx \\
      --framework-type sfia-9 \\
      --framework-version 9.0

Expected result: ~120 rows in ``framework_skills`` and ~500–800 rows in
``framework_skill_levels``. Idempotent (ON CONFLICT DO UPDATE).

Expected column layout in the ``Skills`` sheet (1-indexed):
  A: Code, B: URL (ignored), C: Skill name, D: Category, E: Subcategory,
  F: Overall description, G: Guidance notes,
  H–N: Level 1–7 descriptions.
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
    openai_api_key: str,
) -> None:
    import asyncpg
    import openpyxl

    from src.adapters.openai_embedder import OpenAIEmbeddingService

    embedder = OpenAIEmbeddingService(api_key=openai_api_key)
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
                    "Run create_framework.py first."
                )

        wb = openpyxl.load_workbook(excel_path, data_only=True)
        sheet = wb["Skills"]

        chunks_ingested = 0
        skills_upserted = 0
        failed = 0

        async with pool.acquire() as conn:
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row[0]:
                    continue

                try:
                    skill_code = str(row[0]).strip()
                    # row[1] is URL — ignored
                    skill_name = str(row[2] or "").strip()
                    category = str(row[3] or "").strip()
                    subcategory = str(row[4]).strip() if row[4] else None
                    overall_desc = str(row[5] or "").strip()
                    guidance = str(row[6]).strip() if row[6] else None
                    # Columns H–N are level 1–7 descriptions (indices 7–13)
                    level_descriptions = [
                        str(row[i]).strip() if i < len(row) and row[i] else ""
                        for i in range(7, 14)
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

                        content = (
                            f"Framework: SFIA 9\n"
                            f"Skill: {skill_name} ({skill_code})\n"
                            f"Category: {category}"
                            f"{f' > {subcategory}' if subcategory else ''}\n"
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
                            str(embedding),  # asyncpg serialises vector as text
                        )
                        chunks_ingested += 1

                except Exception as exc:
                    print(f"  ERROR ingesting skill '{row[0]}': {exc}")
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
        description="Ingest SFIA skills + embeddings into framework_skills / framework_skill_levels"
    )
    parser.add_argument("--excel", required=True, help="Path to sfia-9.xlsx")
    parser.add_argument("--framework-type", default="sfia-9")
    parser.add_argument("--framework-version", default="9.0")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
    )
    parser.add_argument(
        "--openai-api-key",
        default=os.environ.get("OPENAI_API_KEY", ""),
        help="OpenAI API key for text-embedding-3-small",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is not set")
    if not args.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is not set")

    asyncio.run(
        ingest_sfia_skills(
            excel_path=args.excel,
            framework_type=args.framework_type,
            framework_version=args.framework_version,
            database_url=args.database_url,
            openai_api_key=args.openai_api_key,
        )
    )


if __name__ == "__main__":
    main()
