"""Create a framework record in the ``frameworks`` table.

Usage::

    python -m src.scripts.create_framework \\
      --framework-type sfia-9 \\
      --framework-version 9.0 \\
      --framework-name "SFIA 9" \\
      --rubric-file docs/development/rubrics/sfia-9-rubric.txt

Expected result: 1 row inserted (idempotent — re-running updates in place).
"""

from __future__ import annotations

import argparse
import asyncio
import os


async def create_framework(
    *,
    framework_type: str,
    framework_version: str,
    framework_name: str,
    rubric: str,
    database_url: str,
) -> None:
    import asyncpg

    pool = await asyncpg.create_pool(database_url)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO frameworks (type, version, name, rubric, is_active)
                VALUES ($1, $2, $3, $4, true)
                ON CONFLICT (type, version)
                DO UPDATE SET
                    name      = EXCLUDED.name,
                    rubric    = EXCLUDED.rubric,
                    is_active = true,
                    updated_at = now()
                RETURNING id, type, version
                """,
                framework_type,
                framework_version,
                framework_name,
                rubric,
            )
        print(
            f"Framework upserted: id={row['id']} "
            f"type={row['type']} version={row['version']}"
        )
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create / update a framework record")
    parser.add_argument("--framework-type", required=True)
    parser.add_argument("--framework-version", required=True)
    parser.add_argument("--framework-name", required=True)
    parser.add_argument("--rubric-file", required=True)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="PostgreSQL connection URL (default: $DATABASE_URL)",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is not set")

    with open(args.rubric_file) as f:
        rubric = f.read().strip()

    asyncio.run(
        create_framework(
            framework_type=args.framework_type,
            framework_version=args.framework_version,
            framework_name=args.framework_name,
            rubric=rubric,
            database_url=args.database_url,
        )
    )


if __name__ == "__main__":
    main()
