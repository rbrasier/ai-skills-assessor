"""Extract SFIA Generic Attributes from the Excel file and populate ``framework_attributes``.

Usage::

    python -m src.scripts.extract_sfia_attributes \\
      --excel docs/development/contracts/sfia-9.xlsx \\
      --framework-type sfia-9 \\
      --framework-version 9.0

Expected result: 35 rows (5 attributes × 7 levels). Idempotent.

The ``Attributes`` sheet is expected to have attribute names in column A and
level descriptors in columns B–H (levels 1–7).
"""

from __future__ import annotations

import argparse
import asyncio
import os


async def extract_sfia_attributes(
    *,
    excel_path: str,
    framework_type: str,
    framework_version: str,
    database_url: str,
) -> None:
    import asyncpg
    import openpyxl

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
        sheet = wb["Attributes"]

        rows_inserted = 0
        rows_skipped = 0

        async with pool.acquire() as conn:
            for row in sheet.iter_rows(min_row=2, values_only=True):
                attribute = row[0]
                if not attribute:
                    continue

                for level in range(1, 8):
                    description = row[level] if len(row) > level else None
                    if not description:
                        rows_skipped += 1
                        continue

                    await conn.execute(
                        """
                        INSERT INTO framework_attributes
                            (framework_id, attribute, level, description)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (framework_id, attribute, level)
                        DO UPDATE SET description = EXCLUDED.description
                        """,
                        framework_id,
                        str(attribute).strip(),
                        level,
                        str(description).strip(),
                    )
                    rows_inserted += 1

        print(
            f"Extracted {rows_inserted} attribute descriptors "
            f"({rows_skipped} empty cells skipped) for '{framework_type}'"
        )
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract SFIA Generic Attributes into framework_attributes"
    )
    parser.add_argument("--excel", required=True, help="Path to sfia-9.xlsx")
    parser.add_argument("--framework-type", default="sfia-9")
    parser.add_argument("--framework-version", default="9.0")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is not set")

    asyncio.run(
        extract_sfia_attributes(
            excel_path=args.excel,
            framework_type=args.framework_type,
            framework_version=args.framework_version,
            database_url=args.database_url,
        )
    )


if __name__ == "__main__":
    main()
