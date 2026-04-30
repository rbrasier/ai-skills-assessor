# PHASE-5 Implementation: RAG Knowledge Base, Framework Configuration & SFIA Data Ingestion

## Reference
- **Phase Document:** `docs/development/implementated/v0.5/v0.5-phase-5-rag-knowledge-base.md`
- **Implementation Date:** 2026-04-30
- **Status:** In Progress

---

## Verification Record

### PRDs Approved
| PRD | Title | Status | Verified |
|-----|-------|--------|---------|
| PRD-002 | Assessment Interview Workflow | 🟢 Approved | 2026-04-30 |

### ADRs Accepted
| ADR | Title | Status | Verified |
|-----|-------|--------|---------|
| ADR-001 | Hexagonal Architecture (Ports & Adapters) | Accepted | 2026-04-30 |
| ADR-003 | Monorepo Structure with pnpm Workspaces + Turborepo | Accepted | 2026-04-30 |
| ADR-005 | RAG & Vector Store Strategy (pgvector, Framework-Type Metadata) | Accepted | 2026-04-30 |

---

## Phase Summary

Establishes the RAG knowledge base layer for the voice assessment platform: a normalized 4-table PostgreSQL schema for SFIA framework configuration, OpenAI-backed embedding service, pgvector similarity search, a static cached system prompt builder, and state-transition RAG context injection into the Pipecat flow controller.

---

## Phase Scope

### Deliverables
- Prisma schema: 4 new models (`Framework`, `FrameworkAttributes`, `FrameworkSkills`, `FrameworkSkillLevels`); `SkillEmbedding` model removed
- `IEmbeddingService` port (`apps/voice-engine/src/domain/ports/embedding_service.py`)
- `IKnowledgeBase` port — full replacement (`apps/voice-engine/src/domain/ports/knowledge_base.py`)
- `OpenAIEmbeddingService` adapter (`apps/voice-engine/src/adapters/openai_embedder.py`)
- `PgVectorKnowledgeBase` adapter (`apps/voice-engine/src/adapters/pgvector_knowledge_base.py`)
- `SystemPromptBuilder` (`apps/voice-engine/src/flows/system_prompt_builder.py`)
- SFIA 9 ingestion scripts: `create_framework.py`, `extract_sfia_attributes.py`, `ingest_sfia_skills.py`
- Updated `SfiaFlowController`: injected `system_prompt` + `knowledge_base`; RAG context at state-transition
- Config renames: `anthropic_model` → `anthropic_in_call_model`; new `anthropic_post_call_model`
- SFIA 9 assessor rubric file: `docs/development/rubrics/sfia-9-rubric.txt`

### Breaking Changes (intentional — no backwards-compat shims)
- `IKnowledgeBase.search_skills()` removed; replaced by `query()` + `query_by_skill_code()`
- `SkillDefinition` dataclass moved from `domain/models/skill.py` to `domain/ports/knowledge_base.py`; old file deleted
- `SFIALevel` enum removed from `domain/models/skill.py`
- `_BOT_PERSONA` constant removed from `SfiaFlowController`; replaced by injected `system_prompt: str`
- `settings.anthropic_model` renamed to `settings.anthropic_in_call_model` in all call sites

### External Dependencies
- Phases 1–4 complete (Prisma setup, voice engine, assessment state machine)
- PostgreSQL with pgvector extension available
- OpenAI API key (for `text-embedding-3-small`)
- SFIA 9 Excel file at `docs/development/contracts/sfia-9.xlsx`

---

## Implementation Strategy

### Approach
Follow the phase document order: database schema first, then ports, then adapters, then ingestion scripts, then voice pipeline integration.

### Build Sequence
1. **Prisma schema** — Add 4 new models, remove `SkillEmbedding`, run migration
2. **Ports** — Replace `IKnowledgeBase`; add `IEmbeddingService`; remove old `SkillDefinition` / `SFIALevel`
3. **Adapters** — `OpenAIEmbeddingService` + `PgVectorKnowledgeBase`
4. **SystemPromptBuilder** — Static cached prompt from DB
5. **Ingestion scripts** — `create_framework.py`, `extract_sfia_attributes.py`, `ingest_sfia_skills.py`
6. **SfiaFlowController updates** — Inject `system_prompt` + `knowledge_base`; RAG at state-transition
7. **Config changes** — Rename fields, update all call sites
8. **Validation** — Run `./validate.sh`

---

## Known Risks and Unknowns

### Risks
- **SFIA data licensing**: Verify BCS licensing terms before ingestion; fallback to a curated 20–30 skill subset if needed
- **Embedding API rate limits during bulk ingestion**: Implement exponential backoff (2s, 4s, 8s, 16s) for 429 responses
- **pgvector index degradation after re-ingestion**: Run `REINDEX` after bulk operations; monitor P95 latency
- **Embedding dimension lock-in**: `text-embedding-3-small` = 1536 dims; switching models requires re-embedding all rows

### Unknowns
- Actual SFIA 9 Excel worksheet column layout (confirmed by inspecting `docs/development/contracts/sfia-9.xlsx` before running ingestion scripts)
- Whether pgvector extension is already enabled in the target DB

### Scope Clarifications
None — implementation follows the phase document exactly.

---

## Implementation Notes

### Part 1: Prisma Schema — 4 New Models
- **Goal:** Add `Framework`, `FrameworkAttributes`, `FrameworkSkills`, `FrameworkSkillLevels` to `packages/database/prisma/schema.prisma`; remove `SkillEmbedding`
- **Acceptance criteria:**
  - All 4 tables created with correct columns, FK constraints, and unique indexes
  - `FrameworkSkillLevels.embedding` typed as `Unsupported("vector(1536)")`
  - `SkillEmbedding` model removed; data migration SQL handles existing rows
  - Migration name: `v0_5_0_add_framework_config_and_skill_levels`
  - pgvector IVFFlat index created via raw SQL post-migration
- **Key decisions going in:**
  - Normalized 4-table design (Option A): skill identity in `FrameworkSkills`, level content + embeddings in `FrameworkSkillLevels`
  - `embedding` column uses `Unsupported` type; raw SQL used for vector queries
- **Blockers:** None — Prisma is set up from Phase 1

### Part 2: Ports — IEmbeddingService & IKnowledgeBase Replacement
- **Goal:** Define `IEmbeddingService` (new); fully replace `IKnowledgeBase` with `query()` + `query_by_skill_code()`; relocate `SkillDefinition` dataclass; delete old `domain/models/skill.py`
- **Acceptance criteria:**
  - `IEmbeddingService` has `embed(text)` and `embed_batch(texts)` abstract methods
  - `IKnowledgeBase` has `query()` and `query_by_skill_code()` with correct signatures
  - `SkillDefinition` dataclass defined in `knowledge_base.py` (not `models/skill.py`)
  - `domain/models/skill.py` deleted (or emptied if other content exists)
  - No references to `search_skills()` or old `SFIALevel` enum remain
- **Blockers:** None

### Part 3: Adapters — OpenAIEmbeddingService & PgVectorKnowledgeBase
- **Goal:** Implement both adapters against the new ports
- **Acceptance criteria:**
  - `OpenAIEmbeddingService` uses `text-embedding-3-small` (1536 dims); batches up to 2048 texts
  - `PgVectorKnowledgeBase` queries pgvector with cosine distance; supports `level_filter` and `skill_codes` filters; `query_by_skill_code()` is a direct lookup (no vector search)
  - Both adapters are dependency-injected — no `new` statements inside core logic
- **Blockers:** Ports (Part 2) must be defined first

### Part 4: SystemPromptBuilder
- **Goal:** Build static cacheable system prompt from DB (framework rubric + Generic Attributes)
- **Acceptance criteria:**
  - `build_cached_system_prompt()` fetches from `frameworks` and `framework_attributes`
  - Built prompt includes bot persona, rubric, and all 35 Generic Attribute level descriptors
  - Method raises `ValueError` if framework not found
  - Result is a plain string — no DB access in `SfiaFlowController`
- **Blockers:** Schema (Part 1) must exist; framework data must be seeded (Part 5)

### Part 5: Ingestion Scripts
- **Goal:** Populate framework tables from SFIA 9 Excel and rubric file
- **Acceptance criteria:**
  - `create_framework.py` inserts 1 row in `frameworks` (`isActive=true`)
  - `extract_sfia_attributes.py` inserts 35 rows in `framework_attributes` (5 attrs × 7 levels)
  - `ingest_sfia_skills.py` inserts ~120 rows in `framework_skills` and ~500–800 rows in `framework_skill_levels`
  - All scripts are idempotent (`ON CONFLICT DO NOTHING` / `DO UPDATE`)
  - Rubric file created at `docs/development/rubrics/sfia-9-rubric.txt`
- **Blockers:** Schema (Part 1) must be migrated; pgvector index created

### Part 6: SfiaFlowController Updates + Config Changes
- **Goal:** Wire `system_prompt` and `knowledge_base` into the controller; inject RAG at state-transition; rename config fields
- **Acceptance criteria:**
  - `__init__()` accepts `system_prompt: str` and `knowledge_base: IKnowledgeBase`; `_BOT_PERSONA` constant removed
  - `handle_skills_identified()` queries `IKnowledgeBase.query_by_skill_code()` per skill; stores result in `self._rag_context`
  - `_build_evidence_gathering_node()` embeds `self._rag_context` in `task_messages` with `>>> SKILL DEFINITIONS START/END` markers
  - No RAG queries in `introduction`, `skill_discovery`, `summary`, `closing` phases
  - `config.py`: `anthropic_model` renamed to `anthropic_in_call_model`; `anthropic_post_call_model` added
  - All references to `settings.anthropic_model` updated in `assessment_pipeline.py` and `bot_runner.py`
- **Blockers:** Ports (Part 2) and adapters (Part 3) must be complete

---

## Decisions Log

> Record every non-obvious technical choice here before moving to the next part. Do not leave empty.

| Date | Part | Decision | Rationale | Files Affected |
|------|------|----------|-----------|----------------|
| 2026-04-30 | — | Initial implementation plan created | — | This document |

---

## Revision History

| Date | Revision | Summary | Status |
|------|----------|---------|--------|
| 2026-04-30 | — | Initial implementation plan | In Progress |

---

## Related Documents
- Phase doc: `docs/development/implementated/v0.5/v0.5-phase-5-rag-knowledge-base.md`
- PRD-002: `docs/development/prd/PRD-002-assessment-interview-workflow.md`
- ADR-001: `docs/development/adr/ADR-001-hexagonal-architecture.md`
- ADR-003: `docs/development/adr/ADR-003-monorepo-structure.md`
- ADR-005: `docs/development/adr/ADR-005-rag-vector-store-strategy.md`
- Assessment Report Contract: `docs/development/contracts/assessment-report-contract.md`
