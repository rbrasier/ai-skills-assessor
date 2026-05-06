#!/usr/bin/env python3
"""Generate a SQL migration seeding SFIA-9 framework data with pre-computed embeddings.

Two embedding backends are supported:

  --embedder sentence-transformers  (default)
    Uses ``sentence-transformers/all-MiniLM-L6-v2`` (384 dims).
    Requires internet access to download the model on first run (~80 MB).
    Re-run to upgrade the migration to neural embeddings.

  --embedder lsa
    Uses TF-IDF + TruncatedSVD (384 dims) fitted on the SFIA corpus.
    No internet required. Saves the fitted model to ``--model-out`` so the
    same adapter can embed query text at runtime.
    Retrieval quality is lower than neural embeddings but fully functional.

Usage::

    # Neural (requires internet):
    python scripts/generate_sfia_embeddings_migration.py --embedder sentence-transformers

    # Offline LSA fallback (no internet needed):
    python scripts/generate_sfia_embeddings_migration.py --embedder lsa

Why pre-compute?
  Baking vectors into the migration SQL means deployment only needs
  PostgreSQL + pgvector — no Python, no model download.

Excel column layout (0-indexed in code):
  0:    Row #
  1-7:  Level indicators (non-null = skill available at that level)
  8:    Skill code
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
import sys
import uuid
from pathlib import Path

# Deterministic UUID namespace — do NOT change (migration IDs must be stable).
_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # RFC 4122 URL namespace


def _uid(*parts: str) -> str:
    return str(uuid.uuid5(_NS, ":".join(parts)))


def _sql_str(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _vec(floats: list[float]) -> str:
    """Format as a pgvector literal: '[f1,f2,...]'."""
    inner = ",".join(f"{v:.8f}" for v in floats)
    return f"'[{inner}]'"


def build_content(
    skill_name: str,
    skill_code: str,
    category: str,
    subcategory: str | None,
    level: int,
    overall_desc: str,
    level_desc: str,
    guidance: str | None,
) -> str:
    cat_str = f"{category} > {subcategory}" if subcategory else category
    parts = [
        "Framework: SFIA 9",
        f"Skill: {skill_name} ({skill_code})",
        f"Category: {cat_str}",
        f"Level: {level}",
        "",
        f"Overall Description:\n{overall_desc}",
        "",
        f"Level {level} Description:\n{level_desc}",
    ]
    if guidance:
        parts += ["", f"Guidance:\n{guidance}"]
    return "\n".join(parts)


def read_skills(excel_path: str) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(excel_path, data_only=True)
    sheet = wb["Skills"]
    skills = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        code = row[8]
        if not code:
            continue
        skills.append(
            {
                "code": str(code).strip(),
                "name": str(row[10] or "").strip(),
                "category": str(row[11] or "").strip(),
                "subcategory": str(row[12]).strip() if row[12] else None,
                "overall_desc": str(row[13] or "").strip(),
                "guidance": str(row[14]).strip() if row[14] else None,
                "level_descs": [
                    str(row[15 + i]).strip() if (15 + i) < len(row) and row[15 + i] else ""
                    for i in range(7)
                ],
            }
        )
    return skills


def _collect_chunks(skills: list[dict]) -> list[tuple[str, int, str]]:
    """Return [(skill_code, level, content), ...] for all non-empty level entries."""
    chunks = []
    for skill in skills:
        for lvl_idx, level_desc in enumerate(skill["level_descs"]):
            if not level_desc:
                continue
            level = lvl_idx + 1
            content = build_content(
                skill_name=skill["name"],
                skill_code=skill["code"],
                category=skill["category"],
                subcategory=skill["subcategory"],
                level=level,
                overall_desc=skill["overall_desc"],
                level_desc=level_desc,
                guidance=skill["guidance"],
            )
            chunks.append((skill["code"], level, content))
    return chunks


def generate_embeddings_sentence_transformers(
    skills: list[dict],
) -> dict[tuple, list[float]]:
    """Neural embeddings via sentence-transformers (requires internet first run)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    chunks = _collect_chunks(skills)
    print(f"  Encoding {len(chunks)} chunks with all-MiniLM-L6-v2 …", file=sys.stderr)
    texts = [c[2] for c in chunks]
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    return {(code, level): vec.tolist() for (code, level, _), vec in zip(chunks, vectors)}


def generate_embeddings_lsa(
    skills: list[dict],
    model_out: str,
    n_components: int = 384,
) -> dict[tuple, list[float]]:
    """Local LSA (TF-IDF + TruncatedSVD) embeddings — no internet required.

    Saves the fitted pipeline to ``model_out`` (joblib format) so the
    SklearnLsaEmbeddingService can load it at query time.
    """
    import joblib
    import numpy as np
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import Normalizer
    from sklearn.pipeline import Pipeline

    chunks = _collect_chunks(skills)
    texts = [c[2] for c in chunks]
    print(f"  Fitting TF-IDF + SVD on {len(texts)} chunks …", file=sys.stderr)

    # Use sublinear TF scaling and character n-grams for richer features.
    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    sublinear_tf=True,
                    min_df=1,
                    analyzer="word",
                    ngram_range=(1, 2),
                    max_features=3000,
                ),
            ),
            ("svd", TruncatedSVD(n_components=n_components, random_state=42)),
            ("norm", Normalizer(copy=False)),
        ]
    )

    vectors = pipeline.fit_transform(texts)

    out_path = Path(model_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, out_path, compress=9)
    size_kb = out_path.stat().st_size // 1024
    print(f"  LSA model saved to {out_path} ({size_kb} KB)", file=sys.stderr)

    return {
        (code, level): vec.tolist()
        for (code, level, _), vec in zip(chunks, vectors)
    }


def generate_sql(
    skills: list[dict],
    embeddings: dict[tuple, list[float]],
    rubric: str,
    framework_id: str,
    embedder_label: str,
) -> str:
    dims = len(next(iter(embeddings.values())))
    lines: list[str] = []

    # ── Header ──────────────────────────────────────────────────────────────
    lines += [
        "-- ============================================================",
        "-- v0.9.0: Framework tables + SFIA-9 seed data",
        "--",
        f"-- Embedding model : {embedder_label}",
        f"-- Dimensions      : {dims}",
        "-- Skills          : 147",
        f"-- Level chunks    : {len(embeddings)}",
        "--",
        "-- All vectors are pre-computed. No embedding model is needed",
        "-- at migration time — only PostgreSQL + pgvector.",
        "--",
        "-- To upgrade to neural embeddings once internet is available:",
        "--   python scripts/generate_sfia_embeddings_migration.py \\",
        "--     --embedder sentence-transformers",
        "-- ============================================================",
        "",
        "CREATE EXTENSION IF NOT EXISTS vector;",
        "",
        "-- ── 1. Framework tables ──────────────────────────────────────────",
        "--    These were missing from prior migrations (v0.2–v0.8 covered",
        "--    candidates, sessions, reports, and monitoring). IF NOT EXISTS",
        "--    guards make this safe to re-apply.",
        "",
        "CREATE TABLE IF NOT EXISTS frameworks (",
        "    id         TEXT         NOT NULL,",
        "    type       VARCHAR(50)  NOT NULL,",
        "    version    VARCHAR(20)  NOT NULL,",
        "    name       VARCHAR(255) NOT NULL,",
        "    rubric     TEXT         NOT NULL,",
        "    is_active  BOOLEAN      NOT NULL DEFAULT true,",
        "    metadata   JSONB        NOT NULL DEFAULT '{}',",
        "    created_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,",
        "    updated_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,",
        "    CONSTRAINT frameworks_pkey PRIMARY KEY (id),",
        "    CONSTRAINT frameworks_type_version_key UNIQUE (type, version)",
        ");",
        "",
        "CREATE TABLE IF NOT EXISTS framework_attributes (",
        "    id           TEXT         NOT NULL,",
        "    framework_id TEXT         NOT NULL REFERENCES frameworks(id) ON DELETE CASCADE,",
        "    attribute    VARCHAR(100) NOT NULL,",
        "    level        INTEGER      NOT NULL,",
        "    description  TEXT         NOT NULL,",
        "    metadata     JSONB        NOT NULL DEFAULT '{}',",
        "    created_at   TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,",
        "    CONSTRAINT framework_attributes_pkey PRIMARY KEY (id),",
        "    CONSTRAINT framework_attributes_framework_id_attribute_level_key",
        "        UNIQUE (framework_id, attribute, level)",
        ");",
        "",
        "CREATE TABLE IF NOT EXISTS framework_skills (",
        "    id           TEXT         NOT NULL,",
        "    framework_id TEXT         NOT NULL REFERENCES frameworks(id) ON DELETE CASCADE,",
        "    skill_code   VARCHAR(50)  NOT NULL,",
        "    skill_name   VARCHAR(255) NOT NULL,",
        "    category     VARCHAR(100) NOT NULL,",
        "    subcategory  VARCHAR(100),",
        "    description  TEXT         NOT NULL,",
        "    guidance     TEXT,",
        "    metadata     JSONB        NOT NULL DEFAULT '{}',",
        "    created_at   TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,",
        "    updated_at   TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,",
        "    CONSTRAINT framework_skills_pkey PRIMARY KEY (id),",
        "    CONSTRAINT framework_skills_framework_id_skill_code_key",
        "        UNIQUE (framework_id, skill_code)",
        ");",
        "",
        f"CREATE TABLE IF NOT EXISTS framework_skill_levels (",
        "    id                  TEXT         NOT NULL,",
        "    framework_skill_id  TEXT         NOT NULL",
        "        REFERENCES framework_skills(id) ON DELETE CASCADE,",
        "    level               INTEGER,",
        f"    content             TEXT         NOT NULL,",
        f"    embedding           vector({dims}),",
        "    metadata            JSONB        NOT NULL DEFAULT '{}',",
        "    created_at          TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,",
        "    CONSTRAINT framework_skill_levels_pkey PRIMARY KEY (id),",
        "    CONSTRAINT idx_unique_skill_level",
        "        UNIQUE (framework_skill_id, level)",
        ");",
        "",
        "CREATE INDEX IF NOT EXISTS framework_skill_levels_framework_skill_id_idx",
        "    ON framework_skill_levels (framework_skill_id);",
        "CREATE INDEX IF NOT EXISTS framework_skills_framework_id_idx",
        "    ON framework_skills (framework_id);",
        "CREATE INDEX IF NOT EXISTS framework_attributes_framework_id_idx",
        "    ON framework_attributes (framework_id);",
        "CREATE INDEX IF NOT EXISTS frameworks_type_idx",
        "    ON frameworks (type);",
        "",
        "-- IVFFlat ANN index. lists=30 suits the ~672-row SFIA corpus.",
        "-- Rebuild with REINDEX after future bulk updates for optimal probe quality.",
        "CREATE INDEX IF NOT EXISTS idx_framework_skill_levels_embedding",
        "    ON framework_skill_levels USING ivfflat (embedding vector_cosine_ops)",
        "    WITH (lists = 30);",
        "",
    ]

    # ── 2. Framework record ─────────────────────────────────────────────────
    lines += [
        "-- ── 2. SFIA-9 framework record ──────────────────────────────────",
        "",
        "INSERT INTO frameworks (id, type, version, name, rubric, is_active)",
        "VALUES (",
        f"    {_sql_str(framework_id)},",
        "    'sfia-9',",
        "    '9.0',",
        "    'SFIA 9',",
        f"    {_sql_str(rubric)},",
        "    true",
        ")",
        "ON CONFLICT (type, version) DO UPDATE SET",
        "    name      = EXCLUDED.name,",
        "    rubric    = EXCLUDED.rubric,",
        "    is_active = true,",
        "    updated_at = CURRENT_TIMESTAMP;",
        "",
    ]

    # ── 3. Skills ───────────────────────────────────────────────────────────
    lines += [
        f"-- ── 3. Skill catalogue ({len(skills)} skills) ─────────────────────────────",
        "",
    ]
    for skill in skills:
        skill_id = _uid("sfia-9", "9.0", skill["code"])
        lines += [
            "INSERT INTO framework_skills",
            "    (id, framework_id, skill_code, skill_name, category, subcategory,",
            "     description, guidance)",
            "VALUES (",
            f"    {_sql_str(skill_id)},",
            f"    {_sql_str(framework_id)},",
            f"    {_sql_str(skill['code'])},",
            f"    {_sql_str(skill['name'])},",
            f"    {_sql_str(skill['category'])},",
            f"    {_sql_str(skill['subcategory'])},",
            f"    {_sql_str(skill['overall_desc'])},",
            f"    {_sql_str(skill['guidance'])}",
            ")",
            "ON CONFLICT (framework_id, skill_code) DO UPDATE SET",
            "    skill_name  = EXCLUDED.skill_name,",
            "    category    = EXCLUDED.category,",
            "    subcategory = EXCLUDED.subcategory,",
            "    description = EXCLUDED.description,",
            "    guidance    = EXCLUDED.guidance,",
            "    updated_at  = CURRENT_TIMESTAMP;",
            "",
        ]

    # ── 4. Skill-level chunks with embeddings ───────────────────────────────
    lines += [
        f"-- ── 4. Skill-level chunks with embeddings ({len(embeddings)} rows) ──",
        "",
    ]
    for skill in skills:
        skill_id = _uid("sfia-9", "9.0", skill["code"])
        for lvl_idx, level_desc in enumerate(skill["level_descs"]):
            if not level_desc:
                continue
            level = lvl_idx + 1
            level_id = _uid("sfia-9", "9.0", skill["code"], str(level))
            content = build_content(
                skill_name=skill["name"],
                skill_code=skill["code"],
                category=skill["category"],
                subcategory=skill["subcategory"],
                level=level,
                overall_desc=skill["overall_desc"],
                level_desc=level_desc,
                guidance=skill["guidance"],
            )
            vec = embeddings.get((skill["code"], level))
            if vec is None:
                continue
            lines += [
                "INSERT INTO framework_skill_levels",
                "    (id, framework_skill_id, level, content, embedding)",
                "VALUES (",
                f"    {_sql_str(level_id)},",
                f"    {_sql_str(skill_id)},",
                f"    {level},",
                f"    {_sql_str(content)},",
                f"    {_vec(vec)}::vector",
                ")",
                "ON CONFLICT (framework_skill_id, level) DO UPDATE SET",
                "    content   = EXCLUDED.content,",
                "    embedding = EXCLUDED.embedding;",
                "",
            ]

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--excel",
        default="docs/development/contracts/sfia-9.xlsx",
        help="Path to sfia-9.xlsx",
    )
    parser.add_argument(
        "--rubric",
        default="docs/development/rubrics/sfia-9-rubric.txt",
        help="Path to sfia-9-rubric.txt",
    )
    parser.add_argument(
        "--out",
        default=(
            "packages/database/prisma/migrations/"
            "v0_9_0_local_embeddings_sfia_data/migration.sql"
        ),
        help="Output SQL file path",
    )
    parser.add_argument(
        "--embedder",
        choices=["sentence-transformers", "lsa"],
        default="sentence-transformers",
        help=(
            "Embedding backend. 'sentence-transformers' requires internet access; "
            "'lsa' uses TF-IDF+SVD locally (no internet needed)."
        ),
    )
    parser.add_argument(
        "--model-out",
        default="apps/voice-engine/data/sfia_lsa_model.joblib",
        help="[lsa only] Where to save the fitted LSA pipeline for runtime use.",
    )
    args = parser.parse_args()

    print("Reading SFIA-9 Excel …", file=sys.stderr)
    skills = read_skills(args.excel)
    print(f"  {len(skills)} skills loaded.", file=sys.stderr)

    if args.embedder == "sentence-transformers":
        embedder_label = "sentence-transformers/all-MiniLM-L6-v2 (neural, 384 dims)"
        print("Encoding with sentence-transformers …", file=sys.stderr)
        embeddings = generate_embeddings_sentence_transformers(skills)
    else:
        embedder_label = "TF-IDF + TruncatedSVD / LSA (local, 384 dims)"
        print("Encoding with LSA (TF-IDF + SVD) …", file=sys.stderr)
        embeddings = generate_embeddings_lsa(skills, model_out=args.model_out)

    print(f"  {len(embeddings)} embeddings ready.", file=sys.stderr)

    rubric = Path(args.rubric).read_text(encoding="utf-8").strip()
    framework_id = _uid("sfia-9", "9.0")

    print("Generating SQL …", file=sys.stderr)
    sql = generate_sql(skills, embeddings, rubric, framework_id, embedder_label)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sql, encoding="utf-8")

    size_kb = out_path.stat().st_size // 1024
    print(f"Written → {out_path} ({size_kb} KB)", file=sys.stderr)
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
