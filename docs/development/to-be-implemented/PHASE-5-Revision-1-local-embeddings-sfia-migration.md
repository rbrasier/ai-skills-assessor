# PHASE-5 Revision 1: Local Embeddings & SFIA-9 Pre-computed Migration

## Status
**Ready for review** — implementation complete on branch `claude/excel-to-vectors-9N2vd`

## Date
2026-05-05

## Parent Phase
[PHASE-5: RAG Knowledge Base](../implemented/v0.5/PHASE-5-implementation-rag-knowledge-base.md)

---

## Problem Statement

Phase 5 implemented RAG using OpenAI's `text-embedding-3-small` API (1536 dims).
This creates two operational problems:

1. **API dependency at ingestion time**: The `ingest_sfia_skills.py` script requires
   an OpenAI API key to populate `framework_skill_levels.embedding`. Environments
   without API access (CI, air-gapped deployments, cost-sensitive dev setups) cannot
   seed the knowledge base.

2. **No pre-computed migration**: The framework tables (`frameworks`, `framework_skills`,
   `framework_skill_levels`) were defined in the Prisma schema (v0.5.0) but their
   SQL migration was never created. Fresh database deployments had no automated path
   to populate the SFIA-9 knowledge base.

Additionally, a bug was discovered in `ingest_sfia_skills.py`: the Excel column indices
were wrong (reading cols A–G when the actual data is in cols I–V), meaning the script
had never successfully ingested real SFIA-9 content.

---

## Decision

Replace the OpenAI API dependency for embeddings with a **locally downloadable Python
library**. Use `sentence-transformers/all-MiniLM-L6-v2` (384 dims) as the primary
neural embedding model — it is the most widely used sentence-transformers model,
requires no API key, and is cached locally after first download (~80 MB).

Additionally, provide a **fully offline fallback** using **TF-IDF + TruncatedSVD
(LSA, 384 dims)** for environments with no internet access. The LSA approach uses
only standard scikit-learn (already a transitive dependency) and needs no model
download at all.

**Pre-computed migration strategy**: Run the embedding model once during development
and bake the resulting vectors directly into the SQL migration file. Deployment then
requires only PostgreSQL + pgvector — no Python, no model download at migration time.
The migration is idempotent (all INSERTs use `ON CONFLICT DO UPDATE`), so re-running
with better-quality embeddings is safe.

---

## Scope

### New Files

| File | Purpose |
|------|---------|
| `apps/voice-engine/src/adapters/sentence_transformers_embedder.py` | Neural embedding adapter (all-MiniLM-L6-v2, 384 dims, no API key) |
| `apps/voice-engine/src/adapters/sklearn_lsa_embedder.py` | Offline LSA adapter (TF-IDF + SVD, 384 dims, no internet needed) |
| `apps/voice-engine/data/sfia_lsa_model.joblib` | Pre-fitted LSA pipeline for offline query-time embedding |
| `scripts/generate_sfia_embeddings_migration.py` | Generates the v0_9_0 SQL migration from the SFIA-9 Excel file |
| `packages/database/prisma/migrations/v0_9_0_local_embeddings_sfia_data/migration.sql` | Complete migration: framework tables DDL + 147 skills + 672 level chunks with embeddings |

### Modified Files

| File | Change |
|------|--------|
| `apps/voice-engine/src/scripts/ingest_sfia_skills.py` | Fix Excel column indices (8/10–14/15–21 not 0/2–6/7–13); add `--embedder` flag supporting `sentence-transformers`, `lsa`, `openai` |
| `packages/database/prisma/schema.prisma` | Change `vector(1536)` → `vector(384)`; add `@map` annotations to align camelCase Prisma fields with snake_case PostgreSQL columns |
| `apps/voice-engine/pyproject.toml` | Add `[scripts]` optional dependency group: `openpyxl`, `sentence-transformers`, `scikit-learn`, `joblib` |

---

## Migration Content (v0_9_0)

The migration SQL is fully self-contained and requires no embedding model at runtime.

```
Framework tables created : frameworks, framework_attributes, framework_skills,
                           framework_skill_levels (vector(384))
SFIA-9 framework record  : 1 row
Skills                   : 147 rows
Level chunks             : 672 rows (with 384-dim embedding vectors)
Embedding backend used   : TF-IDF + TruncatedSVD / LSA (offline generation)
IVFFlat index            : lists=30 (cosine distance, suitable for ~672 rows)
```

### Upgrading to Neural Embeddings

Once internet access is available, re-generate the migration with better vectors:

```bash
pip install -e apps/voice-engine[scripts]
python scripts/generate_sfia_embeddings_migration.py \
  --embedder sentence-transformers \
  --excel docs/development/contracts/sfia-9.xlsx \
  --rubric docs/development/rubrics/sfia-9-rubric.txt
```

Then re-apply the migration (idempotent via `ON CONFLICT DO UPDATE`).

---

## Embedding Dimension Change: 1536 → 384

The new adapters use 384 dimensions instead of OpenAI's 1536.

**Impact on existing data:**
- `skill_embeddings` (v0.4.0 legacy table) — not touched; still `vector(1536)`.
  This table is deprecated and unused since Phase 5 introduced `framework_skill_levels`.
- `framework_skill_levels.embedding` — was declared as `vector(1536)` in the Prisma
  schema but the table had no SQL migration, so no real data existed at that dimension.
  The v0_9_0 migration creates the table as `vector(384)`.

---

## Query-Time Embedding

For the `PgVectorKnowledgeBase` adapter to perform semantic similarity search, the
query text must be embedded with the same model used for ingestion.

| Embedder at ingestion | Embedder at query time |
|-----------------------|------------------------|
| `sentence-transformers` (neural, 384 dims) | `SentenceTransformersEmbeddingService` |
| `lsa` (TF-IDF+SVD, 384 dims) | `SklearnLsaEmbeddingService` (loads `sfia_lsa_model.joblib`) |
| `openai` (legacy, 1536 dims) | `OpenAIEmbeddingService` |

**Note:** If the database was seeded with LSA vectors (the v0_9_0 migration default),
the voice engine must be started with `SklearnLsaEmbeddingService` to get correct
similarity scores. Upgrade to `SentenceTransformersEmbeddingService` by re-running
the generation script with `--embedder sentence-transformers` and then re-applying
the migration.

---

## Running the Ingestion Scripts Manually

If you need to re-embed after a model change (not required for a fresh database):

```bash
# Sentence-transformers (requires internet once to download ~80 MB model):
python -m src.scripts.ingest_sfia_skills \
  --excel docs/development/contracts/sfia-9.xlsx \
  --embedder sentence-transformers

# Offline LSA (requires sfia_lsa_model.joblib):
python -m src.scripts.ingest_sfia_skills \
  --excel docs/development/contracts/sfia-9.xlsx \
  --embedder lsa
```

---

## Acceptance Criteria

- [ ] `v0_9_0_local_embeddings_sfia_data/migration.sql` applies cleanly to a fresh
      PostgreSQL database (with pgvector) from v0.8.0 state
- [ ] After migration: 147 rows in `framework_skills`, 672 rows in
      `framework_skill_levels`, all `embedding` columns non-null
- [ ] `PgVectorKnowledgeBase.query("software testing")` returns ≥1 result
- [ ] `SentenceTransformersEmbeddingService` produces 384-dim vectors (verified
      once internet access is available)
- [ ] `SklearnLsaEmbeddingService` loads `sfia_lsa_model.joblib` and produces
      384-dim vectors without internet
- [ ] `ingest_sfia_skills.py` with `--embedder sentence-transformers` updates
      all 672 chunks without error on a seeded database
- [ ] `ingest_sfia_skills.py` with `--embedder lsa` produces the same 147 skills
      and 672 chunks as the v0_9_0 migration

---

## Non-Goals

- Migrating the deprecated `skill_embeddings` table (v0.4.0) — it is unused
- Ingesting SFIA Generic Attributes (`extract_sfia_attributes.py`) — out of scope
  for this revision; attributes are stored in `framework_attributes` separately
- GPU-accelerated embedding — all local adapters are CPU-compatible

---

## Dependencies

- Phase 5 complete (framework tables, ports, pgvector adapter)
- PostgreSQL with `pgvector` extension (v0.4.0 migration already enables it)
- `sfia-9.xlsx` present at `docs/development/contracts/sfia-9.xlsx`
- `sfia-9-rubric.txt` present at `docs/development/rubrics/sfia-9-rubric.txt`
