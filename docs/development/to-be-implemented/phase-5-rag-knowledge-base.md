# Phase 5: RAG Knowledge Base, Framework Configuration & SFIA Data Ingestion

## Status
To Be Implemented

## Date
2026-04-30

## References
- PRD-002: Assessment Interview Workflow
- ADR-005: RAG & Vector Store Strategy
- Phase 1: Foundation & Monorepo Scaffold (prerequisite — Prisma schema, database setup)
- Phase 2: Basic Voice Engine & Call Tracking (prerequisite — AssessmentSession and call tracking)
- Phase 3: Infrastructure Deployment (prerequisite)
- Phase 4: Assessment Workflow & Interjection (prerequisite — SfiaFlowController state machine)

## Prerequisites

⚠️ **Version Bump Required**: This phase introduces a new Prisma migration (`Framework`, `FrameworkAttributes`, `FrameworkSkills`, and `FrameworkSkillLevels` models) and removes the existing `SkillEmbedding` model. **Before implementation begins**, run:

```bash
/bump-version
```

Choose a MINOR bump (`v0.4.1` → `v0.5.0`). Then create the migration:

```bash
cd packages/database
pnpm prisma migrate dev --name v0_5_0_add_framework_config_and_skill_levels
```

---

## 0. Phase 4 Compatibility — Breaking Changes

Phase 5 makes several **breaking changes** to interfaces established in Phase 1–4. These are intentional clean cutovers; no backwards-compatibility shims are required.

### 0.1 `IKnowledgeBase` port replacement

**File:** `apps/voice-engine/src/domain/ports/knowledge_base.py`

The Phase 1 stub defined `search_skills(query, framework="SFIA", limit)`. Phase 5 **replaces** this entirely with `query()` + `query_by_skill_code()` (see section 1.2). Update all call sites.

### 0.2 `SkillDefinition` model replacement

**File:** `apps/voice-engine/src/domain/models/skill.py`

The Phase 1 `SkillDefinition(framework, code, name, level: SFIALevel, description)` dataclass and the `SFIALevel` enum are **removed**. The replacement `SkillDefinition` is defined in `domain/ports/knowledge_base.py` (see section 1.2). Delete the old file after updating imports.

### 0.3 RAG injection strategy — state-transition only (not per-turn)

The Pipecat Flows architecture sets `task_messages` once when a node is entered; they are not re-evaluated on each subsequent user turn within that state. Per-turn injection via `LLMMessagesFrame` interception was considered and rejected as fragile.

**Chosen approach (Option C):** RAG context is injected once at state-transition time:

- **`skill_discovery` node**: No RAG injection. Skills are unknown at entry; the LLM identifies them through conversation.
- **`evidence_gathering` node**: `handle_skills_identified()` is already called with the identified skill codes before the node is built. The handler queries `IKnowledgeBase` and stores the formatted RAG context. `_build_evidence_gathering_node()` reads this stored context and embeds it in `task_messages`.

This means `SfiaFlowController` receives an `IKnowledgeBase` instance at construction time. The `RAGContextInjector` class described in the original draft is not implemented — the injection logic lives directly in `handle_skills_identified()` and `_build_evidence_gathering_node()`.

### 0.4 `SystemPromptBuilder` injection pattern

`SystemPromptBuilder.build_cached_system_prompt()` is called **once at call initialisation** (in `SFIACallBot`, before `build_sfia_pipeline()` is called). The resulting string is passed into `SfiaFlowController.__init__()` as `system_prompt: str`, replacing the hardcoded `_BOT_PERSONA` constant. The controller never accesses the database directly.

### 0.5 Config field renames

`anthropic_model` is renamed to `anthropic_in_call_model` (default `claude-haiku-4-5`). A new field `anthropic_post_call_model` is added (default `claude-sonnet-4-6`). All existing references to `settings.anthropic_model` in `assessment_pipeline.py` and `bot_runner.py` must be updated.

### 0.6 Prisma schema — `SkillEmbedding` removed

`model SkillEmbedding` is removed from `packages/database/prisma/schema.prisma`. The four new models (`Framework`, `FrameworkAttributes`, `FrameworkSkills`, `FrameworkSkillLevels`) are added. The data migration SQL in section 7 handles moving any existing `skill_embeddings` rows before the old table is dropped.

### 0.7 Transcript JSONB bloat — deferred to Phase 6

Phase 4's decisions log flagged that storing transcripts in the session `metadata` JSONB column may become unwieldy for long calls. Moving transcripts to a dedicated table is deferred to Phase 6.

---

## Objective

Establish a tiered prompt architecture with Claude's native caching and state-transition RAG injection:

1. **Static system prompt** (fetched from DB once at call init, cached by Claude): Framework-agnostic assessor behavioral rubric + Generic Attributes definitions per framework
2. **State-transition RAG context** (injected once when entering `evidence_gathering`): Skill definitions retrieved from pgvector based on identified skill codes
3. **SFIA 9 data ingestion**: Extract skill definitions and attributes from the official SFIA 9 Excel file, store embeddings, and pre-populate the assessment system

---

## 1. Deliverables

### 1.1 Database Schema — Framework Configuration Tables (Option A: Normalized)

Add four new Prisma models to `packages/database/prisma/schema.prisma`:

#### 1.1.1 Framework (Master Registry)

Stores framework metadata and assessor behavioral scoring guide:

```prisma
/// Master framework registry. Each (type, version) tuple is a unique framework.
/// The `rubric` field stores assessor behavioral scoring guidance, cached in the
/// system prompt during assessment initialization.
model Framework {
  id        String   @id @default(uuid())
  type      String   @db.VarChar(50)      // e.g., "sfia-9", "togaf", "itil"
  version   String   @db.VarChar(20)      // e.g., "9.0", "10.0"
  name      String   @db.VarChar(255)     // e.g., "SFIA 9", "TOGAF 10"
  rubric    String                         // Assessor behavioral scoring guide (long text)
  isActive  Boolean  @default(true)        // Whether this framework version is available for assessments
  metadata  Json     @default("{}")
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  attributes FrameworkAttributes[]
  skills     FrameworkSkills[]

  @@unique([type, version])
  @@index([type])
  @@map("frameworks")
}
```

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID | Unique framework identifier |
| `type` | VARCHAR(50) | Framework type: "sfia-9", "togaf", "itil" |
| `version` | VARCHAR(20) | Framework version: "9.0", "10.0" |
| `name` | VARCHAR(255) | Human-readable name: "SFIA 9", "TOGAF 10" |
| `rubric` | TEXT | Assessor behavioral scoring guide (200–500 words) |
| `isActive` | BOOLEAN | Whether this framework version is available for assessments |
| `metadata` | JSONB | Extensible (e.g., source URL, licence info, display config) |
| `createdAt` | TIMESTAMPTZ | Creation timestamp |
| `updatedAt` | TIMESTAMPTZ | Last update timestamp |

**Notes:**
- Single source of truth for each framework version
- Rubric stored once (not duplicated across 35 rows)
- Future frameworks (TOGAF, ITIL) require only data insertion, no schema changes

#### 1.1.2 FrameworkAttributes (Generic Attributes)

Stores Generic Attributes definitions per level:

```prisma
/// Generic Attributes (Autonomy, Influence, Complexity, Business Skills, Knowledge)
/// with level-specific descriptors (1-7). One row per (framework, attribute, level).
/// Used to populate the static cached system prompt during assessment initialization.
model FrameworkAttributes {
  id          String    @id @default(uuid())
  frameworkId String
  framework   Framework @relation(fields: [frameworkId], references: [id], onDelete: Cascade)
  attribute   String    @db.VarChar(100)   // e.g., "Autonomy", "Influence"
  level       Int                           // 1-7
  description String                        // Level-specific definition
  metadata    Json      @default("{}")
  createdAt   DateTime  @default(now())

  @@unique([frameworkId, attribute, level])
  @@index([frameworkId])
  @@map("framework_attributes")
}
```

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID | Unique attribute identifier |
| `frameworkId` | UUID | Foreign key → frameworks.id (CASCADE on delete) |
| `attribute` | VARCHAR(100) | Attribute: "Autonomy", "Influence", "Complexity", "Business Skills", "Knowledge" |
| `level` | INT | Responsibility level 1–7 |
| `description` | TEXT | Level-specific definition text |
| `metadata` | JSONB | Extensible (e.g., sort order, display hints, related attributes) |
| `createdAt` | TIMESTAMPTZ | Creation timestamp |

**Notes:**
- SFIA 9: 35 rows (5 attributes × 7 levels)
- One row per framework+attribute+level combination
- Loaded into system prompt during assessment initialization

#### 1.1.3 FrameworkSkills (Skill Catalog)

Registers the skills that exist within a framework — one row per skill. This is the identity record for a skill; level-specific content lives in `FrameworkSkillLevels`.

```prisma
/// Skill catalog for a framework. One row per skill (code + name + categories).
/// Separates skill identity from level-specific content and embeddings.
model FrameworkSkills {
  id          String    @id @default(uuid())
  frameworkId String
  framework   Framework @relation(fields: [frameworkId], references: [id], onDelete: Cascade)
  skillCode   String    @db.VarChar(50)    // e.g., "PROG", "DENG", "SCTY"
  skillName   String    @db.VarChar(255)   // e.g., "Programming/Software Development"
  category    String    @db.VarChar(100)   // e.g., "Development and implementation"
  subcategory String?   @db.VarChar(100)   // e.g., "Software design" (optional)
  description String                        // Overall skill description
  guidance    String?                       // Guidance notes (optional)
  metadata    Json      @default("{}")
  createdAt   DateTime  @default(now())
  updatedAt   DateTime  @updatedAt

  levels      FrameworkSkillLevels[]

  @@unique([frameworkId, skillCode])
  @@index([frameworkId])
  @@map("framework_skills")
}
```

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID | Unique skill identifier |
| `frameworkId` | UUID | Foreign key → frameworks.id (CASCADE on delete) |
| `skillCode` | VARCHAR(50) | Framework skill code: "PROG", "DENG", "CLOP", "SCTY" |
| `skillName` | VARCHAR(255) | Human-readable skill name: "Programming/Software Development" |
| `category` | VARCHAR(100) | Top-level category: "Development and implementation" |
| `subcategory` | VARCHAR(100) | Sub-category: "Software design" (nullable) |
| `description` | TEXT | Overall skill description (framework-level, not level-specific) |
| `guidance` | TEXT | Guidance notes for assessors (nullable) |
| `metadata` | JSONB | Extensible (e.g., related skill codes, tags, display order) |
| `createdAt` | TIMESTAMPTZ | Creation timestamp |
| `updatedAt` | TIMESTAMPTZ | Last update timestamp |

**Notes:**
- SFIA 9: ~120 rows (one per skill code)
- Acts as the join point between `Framework` and `FrameworkSkillLevels`
- Skill identity data (code, name, categories, overall description) is stored once here rather than duplicated across every level row

### 1.2 Ports: IEmbeddingService & IKnowledgeBase (Port Definitions)

Define two ports in `apps/voice-engine/src/domain/ports/`. **Note:** `knowledge_base.py` already exists as a Phase 1 stub — Phase 5 **replaces** it entirely (see section 0.1). `embedding_service.py` is a new file.

#### 1.2.1 IEmbeddingService

**File:** `apps/voice-engine/src/domain/ports/embedding_service.py`

```python
from abc import ABC, abstractmethod

class IEmbeddingService(ABC):
    """Port for embedding text into vectors for RAG retrieval."""
    
    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        ...
    
    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in one API call."""
        ...
```

#### 1.2.2 IKnowledgeBase

**File:** `apps/voice-engine/src/domain/ports/knowledge_base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class SkillDefinition:
    skill_code: str
    skill_name: str
    category: str
    subcategory: str | None
    level: int | None
    content: str              # The full embedding text
    similarity: float | None  # Relevance score (0-1)
    framework_type: str

class IKnowledgeBase(ABC):
    @abstractmethod
    async def query(
        self,
        text: str,
        framework_type: str = "sfia-9",
        top_k: int = 5,
        level_filter: int | None = None,
        skill_codes: list[str] | None = None,
    ) -> list[SkillDefinition]:
        """
        Query the knowledge base for skill definitions relevant to the given text.
        
        Args:
            text: Query text to embed and search on
            framework_type: Which framework (default: sfia-9)
            top_k: Max results to return
            level_filter: Restrict to a specific level (1-7)
            skill_codes: Restrict to specific skill codes (for targeted probing)
        
        Returns:
            List of SkillDefinition ordered by relevance (highest first)
        """
        ...
    
    @abstractmethod
    async def query_by_skill_code(
        self,
        skill_code: str,
        framework_type: str = "sfia-9",
    ) -> list[SkillDefinition]:
        """Retrieve all levels for a specific skill (no vector search)."""
        ...
```

### 1.1.4 FrameworkSkillLevels (Level-Specific Content & Embeddings)

Stores level-specific content and vector embeddings for RAG retrieval. One row per (skill, level) combination. Skill identity data lives in `FrameworkSkills`.

```prisma
/// Level-specific content and embeddings for framework skills.
/// One row per (skill, level) combination.
/// The `embedding` column is Unsupported because Prisma lacks native pgvector support;
/// queries use raw SQL. See section 1.4 for raw SQL index creation.
model FrameworkSkillLevels {
  id               String          @id @default(uuid())
  frameworkSkillId String
  frameworkSkill   FrameworkSkills @relation(fields: [frameworkSkillId], references: [id], onDelete: Cascade)
  level            Int?                              // 1-7; NULL for skill summary
  content          String                            // Chunked text for embedding (level desc + overall context)
  embedding        Unsupported("vector(1536)")?     // OpenAI text-embedding-3-small
  metadata         Json            @default("{}")
  createdAt        DateTime        @default(now())

  @@unique([frameworkSkillId, level], name: "idx_unique_skill_level")
  @@index([frameworkSkillId])
  @@map("framework_skill_levels")
}
```

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID | Unique level record identifier |
| `frameworkSkillId` | UUID | Foreign key → framework_skills.id (CASCADE on delete) |
| `level` | INT | Responsibility level 1–7 (NULL for skill-level summary row) |
| `content` | TEXT | Chunked text for embedding (level descriptor + overall skill context) |
| `embedding` | vector(1536) | OpenAI text-embedding-3-small vector (for similarity search) |
| `metadata` | JSONB | Extensible (e.g., keywords, example evidence, related skill codes) |
| `createdAt` | TIMESTAMPTZ | Creation timestamp |

**Notes:**
- Skill identity (code, name, category, subcategory, overall description) is resolved via JOIN to `FrameworkSkills` — not stored here
- SFIA 9: ~500–800 rows across ~120 skills × varying levels
- See section 1.4 for pgvector IVFFlat index creation (raw SQL, post-migration)

**Migration note**:
- The existing `model SkillEmbedding` is **removed** from `packages/database/prisma/schema.prisma` as part of this phase. The four new models (`Framework`, `FrameworkAttributes`, `FrameworkSkills`, `FrameworkSkillLevels`) are added in its place.
- The data migration SQL in section 7 handles migrating any existing `skill_embeddings` rows before dropping the old table.
- Run `pnpm prisma migrate dev --name v0_5_0_add_framework_config_and_skill_levels` to apply the Prisma schema changes.

### 1.4 pgvector Index Creation

**Post-migration**, create the IVFFlat index for efficient vector similarity search. Run this **once** against the production database:

```sql
-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create IVFFlat index for approximate nearest-neighbor search
CREATE INDEX idx_framework_skill_levels_embedding
    ON framework_skill_levels
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Covering index for skill lookups within a framework (used by query_by_skill_code)
CREATE INDEX idx_framework_skill_levels_skill_id
    ON framework_skill_levels (framework_skill_id);
```

**Note**: After bulk ingestion or re-ingestion, run `REINDEX idx_framework_skill_levels_embedding;` to maintain index quality.

### 1.5 SFIA 9 Data Extraction & Ingestion

**Source**: The official SFIA 9 Excel file at `docs/development/contracts/sfia-9.xlsx` contains four worksheets:
- **Skills**: Skill code, name, category, subcategory, and level descriptions (1-7)
- **Attributes**: Generic Attributes (Autonomy, Influence, Complexity, Business Skills, Knowledge) with level-specific text
- **Levels of responsibility**: Detailed guidance for each level (1-7)
- **Read Me Notes**: Licensing and copyright

#### 1.5.1 Extract Framework Attributes

**File:** `apps/voice-engine/src/scripts/extract_sfia_attributes.py`

Extracts the five Generic Attributes from the SFIA Excel "Attributes" sheet and populates the `FrameworkAttributes` table:

```python
import openpyxl
import asyncpg

async def extract_sfia_attributes(
    excel_path: str,
    db_pool: asyncpg.Pool,
    framework_type: str = "sfia-9",
    framework_version: str = "9.0",
):
    """
    Extract SFIA 9 Generic Attributes from Excel and populate FrameworkAttributes.
    
    SFIA defines 5 attributes: Autonomy, Influence, Complexity, Business Skills, Knowledge.
    Each has 7-level descriptors.
    """
    wb = openpyxl.load_workbook(excel_path)
    attributes_sheet = wb["Attributes"]
    
    # Parse worksheet (assumes format: attribute name in col A, level 1 desc in col B, level 2 in col C, etc.)
    rows_inserted = 0
    
    async with db_pool.acquire() as conn:
        # Resolve framework_id from type + version
        framework_id = await conn.fetchval(
            "SELECT id FROM frameworks WHERE type = $1 AND version = $2",
            framework_type, framework_version,
        )
        
        for row in attributes_sheet.iter_rows(min_row=2):  # Skip header
            attribute = row[0].value  # e.g., "Autonomy"
            
            for level in range(1, 8):
                description = row[level].value  # Columns B-H = levels 1-7
                if not description:
                    continue
                
                await conn.execute(
                    """
                    INSERT INTO framework_attributes 
                        (framework_id, attribute, level, description)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT DO NOTHING
                    """,
                    framework_id, attribute, level, description,
                )
                rows_inserted += 1
    
    print(f"Extracted {rows_inserted} attribute descriptors for {framework_type}")
```

#### 1.5.2 Extract and Ingest SFIA Skills

**File:** `apps/voice-engine/src/scripts/ingest_sfia_skills.py`

Extracts skill definitions from the SFIA Excel "Skills" sheet, upserts into `FrameworkSkills`, generates level embeddings, and upserts into `FrameworkSkillLevels`:

```python
import openpyxl
import asyncpg
from domain.ports.embedding_service import IEmbeddingService

async def ingest_sfia_skills(
    excel_path: str,
    db_pool: asyncpg.Pool,
    embedder: IEmbeddingService,
    framework_type: str = "sfia-9",
    framework_version: str = "9.0",
):
    """
    Extract SFIA skills from Excel, upsert into framework_skills and framework_skill_levels.
    
    Expected columns in 'Skills' sheet:
    - Code, URL, Skill, Category, Subcategory, Overall description, Guidance notes
    - Level 1 description, Level 2 description, ..., Level 7 description
    """
    wb = openpyxl.load_workbook(excel_path)
    skills_sheet = wb["Skills"]
    
    chunks_ingested = 0
    failed = 0
    
    async with db_pool.acquire() as conn:
        framework_id = await conn.fetchval(
            "SELECT id FROM frameworks WHERE type = $1 AND version = $2",
            framework_type, framework_version,
        )
        
        for row in skills_sheet.iter_rows(min_row=2, values_only=True):
            try:
                skill_code, _, skill_name, category, subcategory, *descriptions = row
                
                # Descriptions: [overall, guidance, level 1, level 2, ..., level 7]
                overall_desc = descriptions[0] or ""
                guidance = descriptions[1] or ""
                level_descriptions = descriptions[2:9]  # 7 levels
                
                # Upsert skill identity into framework_skills
                framework_skill_id = await conn.fetchval(
                    """
                    INSERT INTO framework_skills
                        (framework_id, skill_code, skill_name, category, subcategory, description, guidance)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (framework_id, skill_code)
                    DO UPDATE SET
                        skill_name  = EXCLUDED.skill_name,
                        description = EXCLUDED.description,
                        guidance    = EXCLUDED.guidance
                    RETURNING id
                    """,
                    framework_id, skill_code, skill_name, category, subcategory,
                    overall_desc, guidance or None,
                )
                
                for level, level_desc in enumerate(level_descriptions, start=1):
                    if not level_desc:
                        continue
                    
                    # Compose chunk: level-specific content with skill context
                    content = (
                        f"Framework: SFIA 9\n"
                        f"Skill: {skill_name} ({skill_code})\n"
                        f"Category: {category}"
                        f"{f' > {subcategory}' if subcategory else ''}\n"
                        f"Level: {level}\n\n"
                        f"Overall Description:\n{overall_desc}\n\n"
                        f"Level {level} Description:\n{level_desc}\n\n"
                        f"Guidance:\n{guidance}"
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
                        framework_skill_id, level, content, embedding,
                    )
                    chunks_ingested += 1
            
            except Exception as e:
                print(f"Error ingesting skill {row[0]}: {e}")
                failed += 1
    
    print(f"Ingested {chunks_ingested} skill-level chunks ({failed} failed)")
```

**Ingestion instructions**:
1. Run `extract_sfia_attributes.py` first (populates `framework_attributes`)
2. Run `ingest_sfia_skills.py` (upserts `framework_skills` rows then `framework_skill_levels` rows)
3. Expected result: ~120 rows in `framework_skills` and ~500–800 rows in `framework_skill_levels`

### 1.6 OpenAIEmbeddingService Adapter

**File:** `apps/voice-engine/src/adapters/openai_embedder.py`

Implements the `IEmbeddingService` port using OpenAI's `text-embedding-3-small`:

```python
from openai import AsyncOpenAI
from domain.ports.embedding_service import IEmbeddingService

class OpenAIEmbeddingService(IEmbeddingService):
    """Adapter for OpenAI embedding API (text-embedding-3-small)."""
    
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        # Validate model dimension (1536 for -small, 3072 for -large)
        self.dimension = 1536 if model.endswith("-small") else 3072
    
    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        response = await self.client.embeddings.create(
            input=text,
            model=self.model,
        )
        return response.data[0].embedding
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Batches up to 2048 per API call."""
        response = await self.client.embeddings.create(
            input=texts,
            model=self.model,
        )
        return [item.embedding for item in response.data]
```

**Embedding strategy**: Use `text-embedding-3-small` (1536 dims) for cost efficiency during ingestion. If retrieval quality degrades, upgrade to `-large` (3072 dims) and re-embed.

### 1.7 PgVectorKnowledgeBase Adapter

**File:** `apps/voice-engine/src/adapters/pgvector_knowledge_base.py`

**Replaces** the Phase 1 stub in the same file (which raised `NotImplementedError`). Implements the `IKnowledgeBase` port using PostgreSQL pgvector:

```python
import asyncpg
from domain.ports.knowledge_base import IKnowledgeBase, SkillDefinition
from domain.ports.embedding_service import IEmbeddingService

class PgVectorKnowledgeBase(IKnowledgeBase):
    """Adapter for pgvector-based skill retrieval from PostgreSQL."""
    
    def __init__(self, db_pool: asyncpg.Pool, embedder: IEmbeddingService):
        self.db_pool = db_pool
        self.embedder = embedder
    
    async def query(
        self,
        text: str,
        framework_type: str = "sfia-9",
        top_k: int = 5,
        level_filter: int | None = None,
        skill_codes: list[str] | None = None,
    ) -> list[SkillDefinition]:
        """Query pgvector for relevant skill definitions."""
        embedding = await self.embedder.embed(text)
        
        conditions = ["f.type = $2"]
        params = [embedding, framework_type]
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
        
        query = f"""
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
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
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
        """Direct lookup: retrieve all levels for a skill (no vector search)."""
        query = """
            SELECT fs.skill_code, fs.skill_name, fs.category, fs.subcategory,
                   fsl.level, fsl.content, f.type AS framework_type
            FROM framework_skill_levels fsl
            JOIN framework_skills fs ON fs.id = fsl.framework_skill_id
            JOIN frameworks f ON f.id = fs.framework_id
            WHERE f.type = $1 AND fs.skill_code = $2
            ORDER BY fsl.level ASC
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, framework_type, skill_code)
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
```

### 1.8 Static Cached System Prompt Builder

**File:** `apps/voice-engine/src/flows/system_prompt_builder.py`

Constructs the static, cacheable system prompt that includes bot persona, assessor rubric, and Generic Attributes definitions. Fetches from `frameworks` and `framework_attributes` tables.

**Injection pattern**: `build_cached_system_prompt()` is called **once** in `SFIACallBot` at call initialisation (before `build_sfia_pipeline()`). The resulting string is passed to `SfiaFlowController.__init__(system_prompt=...)` and replaces the hardcoded `_BOT_PERSONA` constant. The controller never accesses the database directly. The prompt is then passed as `role_message` in each node config, allowing Claude to cache it across turns.

```python
import asyncpg
from domain.ports.knowledge_base import IKnowledgeBase

class SystemPromptBuilder:
    """Builds the static system prompt for caching by Claude."""
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
    
    async def build_cached_system_prompt(
        self,
        framework_type: str = "sfia-9",
        framework_version: str = "9.0",
    ) -> str:
        """
        Build the static system prompt, fetching framework-specific rubric
        and Generic Attributes definitions from the database.
        
        This prompt is designed to be cached by Claude (at the system level),
        so updates are infrequent and the cache persists across multiple calls.
        """
        # Fetch framework record (includes rubric)
        framework = await self._fetch_framework(framework_type, framework_version)
        if not framework:
            raise ValueError(f"Framework {framework_type} {framework_version} not found")
        
        rubric = framework['rubric']
        
        # Fetch Generic Attributes definitions (all 7 levels)
        attributes_text = await self._build_attributes_section(framework['id'])
        
        return f"""You are Noa, a warm and professional AI skills assessor from Resonant. \
You conduct structured SFIA-based skills assessments over the phone.

## Assessment Methodology

Your role is to:
1. Conduct a natural, conversational interview (no jargon, no SFIA codes mentioned to the candidate)
2. Listen for evidence of skills and responsibility levels
3. Probe deeper when evidence suggests higher levels of autonomy, influence, or complexity
4. Record claims and map them to framework skills

Keep your language conversational, concise, and encouraging.

## Assessor Behavioral Scoring Rubric

{rubric}

## Framework Generic Attributes Reference

Use these definitions when scoring responsibility levels (1-7):

{attributes_text}

## Instructions for Dynamic RAG Context

When RAG context is injected into the conversation, it will appear as:
>>> RAG CONTEXT START
[Skill definitions and examples]
>>> RAG CONTEXT END

Use these definitions to:
- Ask level-appropriate probing questions
- Validate evidence against framework definitions
- Identify gaps or higher-level demonstrations
- Stay grounded in verifiable, framework-aligned assessments

Never quote framework codes to the candidate. Always translate framework concepts into natural language.
"""
    
    async def _fetch_framework(self, framework_type: str, framework_version: str) -> dict:
        """Fetch framework record from database."""
        async with self.db_pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT id, type, version, name, rubric FROM frameworks WHERE type = $1 AND version = $2",
                framework_type, framework_version
            )
    
    async def _build_attributes_section(self, framework_id: str) -> str:
        """Fetch Generic Attributes and format for system prompt."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT attribute, level, description
                FROM framework_attributes
                WHERE framework_id = $1
                ORDER BY attribute, level
                """,
                framework_id
            )
        
        # Group by attribute
        attributes = {}
        for row in rows:
            attr = row['attribute']
            if attr not in attributes:
                attributes[attr] = []
            attributes[attr].append((row['level'], row['description']))
        
        # Format for prompt
        sections = []
        for attr in sorted(attributes.keys()):
            section = f"### {attr}\n"
            for level, description in attributes[attr]:
                section += f"Level {level}: {description}\n"
            sections.append(section)
        
        return "\n".join(sections)
```

### 1.9 RAG Context Injection — State-Transition Strategy

No separate `RAGContextInjector` class is implemented. RAG context is injected once at state-transition time, directly inside `SfiaFlowController`.

**Injection point**: `handle_skills_identified()` — this handler already fires with identified skill codes before the `evidence_gathering` node is built. It queries the knowledge base and stores the formatted context; `_build_evidence_gathering_node()` reads the stored context and embeds it in `task_messages`.

**Updated `SfiaFlowController` constructor and handler**:

```python
class SfiaFlowController:
    def __init__(
        self,
        *,
        recorder: TranscriptRecorder,
        on_call_ended: Callable[[], Awaitable[None] | None],
        system_prompt: str,                    # replaces _BOT_PERSONA constant
        knowledge_base: IKnowledgeBase,        # new — injected at startup
        framework_type: str = "sfia-9",
    ) -> None:
        self._recorder = recorder
        self._on_call_ended = on_call_ended
        self._system_prompt = system_prompt
        self._knowledge_base = knowledge_base
        self._framework_type = framework_type
        self._identified_skills: list[dict[str, Any]] = []
        self._rag_context: str = ""            # populated by handle_skills_identified

    async def handle_skills_identified(
        self, args: dict[str, Any], flow_manager: Any
    ) -> tuple[None, Any]:
        """Skills extracted from SkillDiscovery — query RAG, then transition."""
        skills = args.get("skills", [])
        self._identified_skills = skills
        skill_codes = [s["skill_code"] for s in skills if "skill_code" in s]

        # Query knowledge base for all identified skill codes
        try:
            results = []
            for code in skill_codes:
                definitions = await self._knowledge_base.query_by_skill_code(
                    skill_code=code,
                    framework_type=self._framework_type,
                )
                results.extend(definitions)
            self._rag_context = _format_rag_context(results) if results else ""
        except Exception:
            logger.exception("SfiaFlow: RAG query failed — proceeding without context")
            self._rag_context = ""

        logger.info(
            "SfiaFlow: skills_identified (%d) → evidence_gathering (rag=%d chars)",
            len(skills), len(self._rag_context),
        )
        self._recorder.set_phase("evidence_gathering")
        return None, _try_build(self._build_evidence_gathering_node)
```

**Updated `_build_evidence_gathering_node()`** — embeds stored RAG context in `task_messages`:

```python
def _build_evidence_gathering_node(self) -> Any:
    FlowsFunctionSchema = _import_flows_schema()
    skills_summary = ", ".join(
        s.get("skill_name", s.get("skill_code", "unknown"))
        for s in self._identified_skills
    ) or "the areas discussed"

    rag_block = (
        f"\n\n>>> SKILL DEFINITIONS START\n{self._rag_context}\n>>> SKILL DEFINITIONS END"
        if self._rag_context else ""
    )

    return {
        "role_message": self._system_prompt,
        "task_messages": [
            {
                "role": "user",
                "content": (
                    f"You are now gathering evidence for: {skills_summary}."
                    f"{rag_block}\n\n"
                    "Use the skill definitions above (if present) to ask level-appropriate "
                    "probing questions. For each skill, ask for a concrete work example. "
                    "Probe for: Autonomy, Influence, Complexity, Knowledge. "
                    "When sufficient evidence is gathered, call evidence_complete."
                ),
            }
        ],
        "functions": [...],  # same as before
    }
```

**Helper** (module-level):

```python
def _format_rag_context(results: list[SkillDefinition]) -> str:
    lines = []
    for skill in results:
        level_str = f" — Level {skill.level}" if skill.level else ""
        lines.append(f"\n**{skill.skill_name} ({skill.skill_code}){level_str}**")
        lines.append(skill.content)
    return "\n".join(lines)
```

**Phase coverage**:

| Phase | RAG behaviour |
|-------|--------------|
| `introduction` | No RAG — fixed consent prompt |
| `skill_discovery` | No RAG — skills unknown at entry |
| `evidence_gathering` | RAG context injected once at node entry (from `handle_skills_identified`) |
| `summary` | No RAG — summarisation prompt only |
| `closing` | No RAG — fixed farewell |

---

## 1.10 Config Changes (`config.py`)

**File:** `apps/voice-engine/src/config.py`

The `anthropic_model` field is **renamed** and a new post-call field is added:

```python
# Before (Phase 4):
anthropic_model: str = "claude-3-5-haiku-latest"

# After (Phase 5):
anthropic_in_call_model: str = "claude-haiku-4-5"       # real-time, low-latency in-call responses
anthropic_post_call_model: str = "claude-sonnet-4-6"    # post-call claim extraction and scoring
```

Update all references to `settings.anthropic_model` in:
- `apps/voice-engine/src/flows/assessment_pipeline.py` → `settings.anthropic_in_call_model`
- `apps/voice-engine/src/flows/bot_runner.py` (if referenced there)

---

## 2. Framework Configuration & SFIA 9 Initialization

### SFIA 9 Data Source

The official SFIA 9 Excel file is located at `docs/development/contracts/sfia-9.xlsx`. It contains:

| Sheet | Content | Usage |
|-------|---------|-------|
| **Skills** | Skill codes, names, categories, level descriptions (1-7) | Ingest into `framework_skills` + `framework_skill_levels` |
| **Attributes** | Generic Attributes (Autonomy, Influence, Complexity, Business Skills, Knowledge) with level-specific text | Populate `framework_attributes` |
| **Levels of responsibility** | Detailed guidance for responsibility levels 1-7 | Reference for assessor rubric |
| **Read Me Notes** | Licensing, copyright, usage terms | Compliance verification |

### SFIA 9 Pre-Load Process

Before deployment, run three scripts in order:

#### Step 1: Create Framework Record

Insert SFIA 9 framework with rubric:

```bash
python apps/voice-engine/src/scripts/create_framework.py \
  --framework-type sfia-9 \
  --framework-version 9.0 \
  --framework-name "SFIA 9" \
  --rubric-file docs/development/rubrics/sfia-9-rubric.txt
```

**Contents of `docs/development/rubrics/sfia-9-rubric.txt`** (assessor guidance):
```
SFIA 9 Assessment Rubric

Scoring Guidelines:
- Level 1-2: Foundation competence, works under routine direction
- Level 3-4: Practitioner, works with some independence, follows established patterns
- Level 5-6: Expert, designs solutions, influences organization
- Level 7: Strategic leader, sets direction, shapes capability

Evidence Scoring:
Listen for concrete examples of:
- Autonomy: How independently do they make decisions?
- Influence: What is their sphere of impact on others?
- Complexity: What scale and ambiguity of problems do they handle?
- Business Skills: How business-aware are they?
- Knowledge: What depth and breadth of technical knowledge?

Map evidence to SFIA skill definitions (provided via RAG context).
Assign level 1-7 based on demonstrated attributes across all five dimensions.
```

Expected result: 1 row in `frameworks` table

#### Step 2: Extract Generic Attributes

Populate `framework_attributes` with SFIA Generic Attributes:

```bash
python apps/voice-engine/src/scripts/extract_sfia_attributes.py \
  --excel docs/development/contracts/sfia-9.xlsx \
  --framework-type sfia-9 \
  --framework-version 9.0
```

Expected result: 35 rows in `framework_attributes` (5 attributes × 7 levels)

#### Step 3: Ingest Skills and Embeddings

Populate `framework_skills` and `framework_skill_levels` with skill definitions and vectors:

```bash
python apps/voice-engine/src/scripts/ingest_sfia_skills.py \
  --excel docs/development/contracts/sfia-9.xlsx \
  --framework-type sfia-9 \
  --framework-version 9.0
```

Expected result: ~120 rows in `framework_skills` and ~500–800 rows in `framework_skill_levels`

### Future Frameworks

To add a new framework (e.g., TOGAF):

1. Prepare an Excel file in the same structure as SFIA 9
2. Extract attributes: `extract_sfia_attributes.py --framework-type togaf --excel togaf.xlsx`
3. Ingest skills: `ingest_sfia_skills.py --framework-type togaf --excel togaf.xlsx`
4. Load rubric: `load_sfia_rubric.py --framework-type togaf --rubric-file togaf-rubric.txt`
5. Query with `framework_type="togaf"` in assessment pipeline

**No schema changes required** — the tiered architecture supports multi-framework deployments.

---

## 3. Runtime Integration with Voice Pipeline

### Tiered Prompt Architecture

The system uses two layers of context, each managed independently:

#### Layer 1: Static Cached System Prompt (Claude caching)

Built once at call initialization, cached by Claude for the entire assessment:

```
┌─────────────────────────────────────────────┐
│ STATIC SYSTEM PROMPT (Claude-cached)        │
├─────────────────────────────────────────────┤
│ • Bot persona (Noa)                         │
│ • Assessment methodology                    │
│ • Assessor behavioral scoring rubric        │
│ • Generic Attributes (Autonomy, Influence,  │
│   Complexity, Business Skills, Knowledge)   │
│   — definitions for all 7 levels            │
│ • Instruction: "Use RAG context below..."   │
└─────────────────────────────────────────────┘
```

This prompt remains unchanged throughout the call and is cached, so subsequent LLM calls only incur token cost for the dynamic layer.

#### Layer 2: State-Transition RAG Context (Pipecat task_messages)

Injected once when entering `evidence_gathering` — embedded directly in that node's `task_messages`:

```
EVIDENCE GATHERING NODE task_messages:
└─ [user]: "{phase instruction}\n\n>>> SKILL DEFINITIONS START\n{skill definitions}\n>>> SKILL DEFINITIONS END\n\n{probing instructions}"
```

RAG context is fetched during `handle_skills_identified()` (the state transition from `skill_discovery`) and stored on the controller. No per-turn queries.

### Call Flow with Tiered Architecture

```
┌─ CALL STARTS ─────────────────────────────┐
│ 1. Create AssessmentSession               │
│ 2. Load framework config (sfia-9)         │
│ 3. Build static system prompt             │
│    - SystemPromptBuilder fetches rubric   │
│    - Fetches FrameworkAttributes (35 rows)│
│    - Returns prompt string                │
│                                            │
│ 4. Initialize SfiaFlowController          │
│    - Inject system_prompt string          │
│    - Inject IKnowledgeBase instance       │
│ 5. Initialize Pipecat pipeline            │
│    - system_prompt passed as role_message │
└────────────────────────────────────────────┘
           ↓
┌─ SKILL DISCOVERY (multiple turns) ────────┐
│ LLM converses using system_prompt only    │
│ No RAG queries during this phase          │
│ LLM calls skills_identified() when ready │
└────────────────────────────────────────────┘
           ↓
┌─ handle_skills_identified() ──────────────┐
│ 1. Store identified skill codes           │
│ 2. Query IKnowledgeBase.query_by_skill_code│
│    for each identified skill              │
│ 3. Format results → self._rag_context     │
│ 4. Transition to evidence_gathering node  │
└────────────────────────────────────────────┘
           ↓
┌─ EVIDENCE GATHERING (multiple turns) ─────┐
│ task_messages contains RAG context baked  │
│ in at node entry — no per-turn queries    │
│ LLM uses skill definitions to probe       │
└────────────────────────────────────────────┘
```

### Latency Targets

| Component | Latency | Notes |
|-----------|---------|-------|
| pgvector query (at state transition) | < 10ms per skill code | IVFFlat index, ~800 embeddings |
| Total RAG overhead at transition | < 50ms | Queries are batched across identified skills |
| Claude API call (with caching) | ~200-500ms | Cached system prompt reduces token cost |

**Cache efficiency**: After the first turn, Claude's cache hit reduces input tokens by ~90% for the static system prompt, reducing both latency and cost.

### Context Update Frequency

| Phase | RAG Behavior |
|-------|--------------|
| **introduction** | No RAG queries; system prompt only |
| **skill_discovery** | No RAG queries; skills unknown |
| **evidence_gathering** | RAG query on every user turn; focused search (top 3, filtered by identified skills) |
| **summary** | No RAG queries; summarization prompt only |
| **closing** | No RAG queries; fixed farewell |

**Debouncing**: If the user speaks multiple short utterances in quick succession (< 500ms between end of STT and next user input), batch them into a single RAG query before LLM call.

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Knowledge base empty or unavailable | Use fallback: skip RAG injection, continue with static prompt |
| Embedding API rate limit | Implement exponential backoff; if limit exceeded, use word-based keyword matching instead of vector search |
| pgvector query returns no results | Return empty RAG context; LLM continues with static knowledge |
| Claude cache miss (new framework loaded) | Cache re-populates on next call; no visible latency impact |

---

## 4. Acceptance Criteria

### Database Schema & Ingestion

- [ ] `Framework` table created with columns: `id`, `type`, `version`, `name`, `rubric`, `isActive`, `metadata`, `createdAt`, `updatedAt`
- [ ] `FrameworkAttributes` table created with columns: `id`, `frameworkId` (FK), `attribute`, `level`, `description`, `metadata`, `createdAt`
- [ ] `FrameworkSkills` table created with columns: `id`, `frameworkId` (FK), `skillCode`, `skillName`, `category`, `subcategory`, `description`, `guidance`, `metadata`, `createdAt`, `updatedAt`
- [ ] `FrameworkSkillLevels` table created with columns: `id`, `frameworkSkillId` (FK), `level`, `content`, `embedding`, `metadata`, `createdAt`
- [ ] `FrameworkSkillLevels.embedding` column is `vector(1536)`
- [ ] pgvector extension enabled; raw SQL migration runs without errors
- [ ] IVFFlat index created on `framework_skill_levels.embedding` with `lists = 100`
- [ ] Create framework script inserts SFIA 9 into `frameworks` table (1 row, `isActive = true`)
- [ ] Extract SFIA attributes script populates `framework_attributes` with 35 rows (5 attributes × 7 levels)
- [ ] Ingest SFIA skills script populates `framework_skills` with ~120 rows and `framework_skill_levels` with 500–800 rows (verified row counts)
- [ ] Ingestion is idempotent: re-running does not duplicate rows (ON CONFLICT DO UPDATE)

### Port & Adapter Implementation

- [ ] `IEmbeddingService` port defined at `domain/ports/embedding_service.py` with `embed(text)` and `embed_batch(texts)` methods
- [ ] `IKnowledgeBase` port **replaced** at `domain/ports/knowledge_base.py` — old `search_skills()` removed; new `query()` and `query_by_skill_code()` methods defined; new `SkillDefinition` dataclass defined here
- [ ] Old `SkillDefinition` and `SFIALevel` removed from `domain/models/skill.py`
- [ ] `OpenAIEmbeddingService` adapter implements `IEmbeddingService`; uses `text-embedding-3-small` (1536 dims)
- [ ] `PgVectorKnowledgeBase` adapter **replaces** the Phase 1 stub; implements `IKnowledgeBase`; queries pgvector and returns `SkillDefinition` objects
- [ ] Both adapters are dependency-injected (not hardcoded in core logic)

### Config Changes

- [ ] `anthropic_model` field **renamed** to `anthropic_in_call_model` with default `claude-haiku-4-5`
- [ ] New `anthropic_post_call_model` field added with default `claude-sonnet-4-6`
- [ ] All references to `settings.anthropic_model` updated to `settings.anthropic_in_call_model` in `assessment_pipeline.py` and `bot_runner.py`

### Static Prompt Architecture (Claude Caching)

- [ ] `SystemPromptBuilder.build_cached_system_prompt()` successfully fetches `Framework` and `FrameworkAttributes` records
- [ ] Query `frameworks WHERE type='sfia-9' AND version='9.0'` returns rubric field; `isActive = true`
- [ ] Query `framework_attributes WHERE frameworkId=...` returns all 35 attribute definitions
- [ ] Built prompt includes bot persona, rubric, and Generic Attributes (5 attrs × 7 levels)
- [ ] Prompt string is injected into `SfiaFlowController.__init__(system_prompt=...)` and used as `role_message` in each node config
- [ ] Cached prompt is reused across all turns in a single call (verified via prompt cache metrics in API response)

### State-Transition RAG Context Injection

- [ ] `SfiaFlowController.__init__()` accepts `knowledge_base: IKnowledgeBase` and `system_prompt: str` arguments
- [ ] `handle_skills_identified()` queries `IKnowledgeBase.query_by_skill_code()` for each identified skill code
- [ ] RAG context formatted with `>>> SKILL DEFINITIONS START / END` markers and stored in `self._rag_context`
- [ ] `_build_evidence_gathering_node()` embeds `self._rag_context` in `task_messages`
- [ ] No RAG queries during `introduction`, `skill_discovery`, `summary`, `closing` phases
- [ ] If knowledge base returns no results, `_rag_context` is empty string and evidence node proceeds without it
- [ ] If `FrameworkSkillLevels` table is empty, RAG context gracefully returns empty string (fallback behavior)

### Integration & Latency

- [ ] End-to-end test: user text → embedding → pgvector query → formatted context → LLM response
- [ ] P95 latency for single RAG query (embedding + pgvector lookup) ≤ 250ms in production database (measured)
- [ ] Debouncing: multiple rapid utterances batch into single RAG query (verified with timing logs)
- [ ] Claude's prompt caching working: verify `cache_creation_input_tokens` and `cache_read_input_tokens` in API response (first turn creates cache, subsequent turns read from cache)
- [ ] Integration with `SfiaFlowController`: `handle_skills_identified()` correctly updates `RAGContextInjector._identified_skills`

### Extensibility

- [ ] Adding a new framework (e.g., TOGAF) requires only data (Excel file + ingestion script), no schema changes
- [ ] Query with `framework_type="togaf"` returns TOGAF results; `framework_type="sfia-9"` returns SFIA results
- [ ] `Framework.rubric` can be updated without redeploying code (long text field)
- [ ] `Framework.isActive` flag allows disabling a framework version without deleting data

## 5. Dependencies

- **Phase 1**: Database schema, port interfaces, Prisma setup
- **Phase 2**: Basic voice infrastructure, AssessmentSession tracking
- **Phase 3**: Infrastructure deployed (PostgreSQL with pgvector extension available)
- **Phase 4**: Assessment workflow state machine (SfiaFlowController, Pipecat flows)
- **External APIs**: OpenAI (for embeddings); PostgreSQL ≥ 13 with pgvector extension
- **Data**: SFIA 9 Excel file (`docs/development/contracts/sfia-9.xlsx`) with licensing verification

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **SFIA data licensing unclear** | Cannot use official SFIA 9 Excel file | Verify BCS licensing terms upfront; prepare fallback with manually curated subset of 20-30 core skills |
| **Embedding API rate limits** | Ingestion script times out during bulk embedding | Implement exponential backoff (2s, 4s, 8s, 16s) for 429 responses; batch up to 2048 texts per request; document in runbook |
| **pgvector index degradation** | Query latency creeps above 250ms after re-ingestion | Run `REINDEX idx_skill_embeddings_embedding` after bulk operations; add monitoring to alert if P95 latency exceeds 300ms |
| **Embedding model change** | Hardcoded 1536 dimensions breaks if switching to 3072-dim model | Store embedding dimension in config (env var or database); migration script to re-embed if swapping models |
| **Knowledge base unavailable (infra failure)** | RAG injection fails, assessment continues | Graceful fallback: skip RAG context, use static system prompt only; log warning; assessment still usable |
| **RAG context too large (many results)** | LLM context window bloated; latency increases | Limit `top_k` to 3–5; truncate individual chunk content if > 500 chars; monitor actual prompt size in logs |

## 7. Implementation Notes

### Development & Testing

- **Test environment**: Use in-memory embedding (mock OpenAI API) for fast unit tests
- **Integration tests**: Use real PostgreSQL with pgvector; ingest small SFIA subset (~10 skills × 7 levels = 70 chunks)
- **Performance tests**: Measure latency of pgvector query with full dataset (~800 chunks); target < 10ms
- **Prompt caching validation**: Use `--verbose` flag with Pipecat to inspect prompt cache headers in API responses

### Deployment Checklist

1. ✅ Run Prisma migration to create `FrameworkAttributes`, `FrameworkSkills`, and `FrameworkSkillLevels` tables
2. ✅ Create pgvector indexes via raw SQL
3. ✅ Verify `docs/development/contracts/sfia-9.xlsx` is available and licensing confirmed
4. ✅ Run extraction script: `extract_sfia_attributes.py`
5. ✅ Run ingestion script: `ingest_sfia_skills.py`
6. ✅ Load assessor rubric: `load_sfia_rubric.py`
7. ✅ Deploy updated `sfia_flow_controller.py` with state-transition RAG injection and injected `system_prompt`
8. ✅ Run integration tests against production database (no real calls)
9. ✅ Monitor first 10 live calls for latency and prompt cache hit rate
10. ✅ Document any schema tweaks or configuration changes in runbook

### Schema Migration (If Migrating from Phase 3)

If `skill_embeddings` exists from Phase 3 with denormalized `frameworkType` + `frameworkVersion` columns, execute this migration:

```sql
-- 1. Create Framework table (if not already created)
CREATE TABLE IF NOT EXISTS frameworks (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type       VARCHAR(50)  NOT NULL,
    version    VARCHAR(20)  NOT NULL,
    name       VARCHAR(255) NOT NULL,
    rubric     TEXT         NOT NULL,
    is_active  BOOLEAN      NOT NULL DEFAULT true,
    metadata   JSONB        NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE(type, version)
);

-- 2. Insert SFIA 9 framework (if not already present)
INSERT INTO frameworks (type, version, name, rubric, is_active)
VALUES ('sfia-9', '9.0', 'SFIA 9', 'Score candidates on 1-7 based on...', true)
ON CONFLICT DO NOTHING;

-- 3. Create FrameworkAttributes table
CREATE TABLE framework_attributes (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id UUID        NOT NULL REFERENCES frameworks(id) ON DELETE CASCADE,
    attribute    VARCHAR(100) NOT NULL,
    level        INT         NOT NULL,
    description  TEXT        NOT NULL,
    metadata     JSONB       NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(framework_id, attribute, level)
);
CREATE INDEX idx_framework_attributes_framework_id ON framework_attributes(framework_id);

-- 4. Create FrameworkSkills table
CREATE TABLE framework_skills (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id UUID         NOT NULL REFERENCES frameworks(id) ON DELETE CASCADE,
    skill_code   VARCHAR(50)  NOT NULL,
    skill_name   VARCHAR(255) NOT NULL,
    category     VARCHAR(100) NOT NULL,
    subcategory  VARCHAR(100),
    description  TEXT         NOT NULL,
    guidance     TEXT,
    metadata     JSONB        NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE(framework_id, skill_code)
);
CREATE INDEX idx_framework_skills_framework_id ON framework_skills(framework_id);

-- 5. Create FrameworkSkillLevels table
CREATE TABLE framework_skill_levels (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_skill_id UUID        NOT NULL REFERENCES framework_skills(id) ON DELETE CASCADE,
    level              INT,
    content            TEXT        NOT NULL,
    embedding          vector(1536),
    metadata           JSONB       NOT NULL DEFAULT '{}',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(framework_skill_id, level)
);
CREATE INDEX idx_framework_skill_levels_skill_id ON framework_skill_levels(framework_skill_id);
CREATE INDEX idx_framework_skill_levels_embedding
    ON framework_skill_levels
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 6. Migrate data from old skill_embeddings into the new two-table structure
-- 6a. Populate framework_skills (distinct skill rows)
INSERT INTO framework_skills (framework_id, skill_code, skill_name, category, subcategory, description)
SELECT DISTINCT
    (SELECT id FROM frameworks WHERE type = framework_type AND version = framework_version),
    skill_code, skill_name, category, subcategory, ''   -- description populated later via ingestion script
FROM skill_embeddings
ON CONFLICT DO NOTHING;

-- 6b. Populate framework_skill_levels from old rows
INSERT INTO framework_skill_levels (framework_skill_id, level, content, embedding, created_at)
SELECT
    fs.id,
    se.level,
    se.content,
    se.embedding,
    se.created_at
FROM skill_embeddings se
JOIN framework_skills fs
    ON fs.skill_code = se.skill_code
    AND fs.framework_id = (
        SELECT id FROM frameworks WHERE type = se.framework_type AND version = se.framework_version
    )
ON CONFLICT DO NOTHING;

-- 7. Verify and cleanup
SELECT COUNT(*) AS skills_migrated      FROM framework_skills;
SELECT COUNT(*) AS skill_levels_migrated FROM framework_skill_levels;
DROP TABLE skill_embeddings;
```

### Revision History

| Date | Change | Notes |
|------|--------|-------|
| 2026-04-30 | Phase 4 compatibility audit + design decisions | Resolved 10 inconsistencies between Phase 4 implementation and Phase 5 plan: (1) RAG injection changed from per-turn to state-transition only (Option C — injected in `handle_skills_identified` / `_build_evidence_gathering_node`); (2) `IKnowledgeBase` clean cutover from `search_skills()` to `query()` + `query_by_skill_code()`; (3) `SkillDefinition` replaced in `domain/ports/knowledge_base.py`, old model removed from `domain/models/skill.py`; (4) `SystemPromptBuilder` result injected into `SfiaFlowController.__init__()` as `system_prompt` string, replacing `_BOT_PERSONA`; (5) `anthropic_model` renamed to `anthropic_in_call_model`, new `anthropic_post_call_model` added; (6) `SkillEmbedding` removed from `schema.prisma`; (7) transcript JSONB bloat deferred to Phase 6; (8) version bump numbers corrected to `0.4.1 → 0.5.0` |
| 2026-04-30 | Refined DB schema — four-table model | Renamed `FrameworkDescriptor` → `FrameworkAttributes`; extracted `FrameworkSkills` catalog table (skill identity); renamed `SkillEmbedding` → `FrameworkSkillLevels` (now FK to `FrameworkSkills`); added `metadata` JSONB to all four tables; added `isActive` flag to `Framework`; updated ingestion scripts, adapter queries, and migration SQL to reflect new structure |
| 2026-04-30 | Refine Phase 5 (Option A Normalized Schema) | Implemented tiered prompt strategy with Claude caching + dynamic RAG; normalized database schema with `Framework` parent table (stores rubric); refactored `SkillEmbedding` to use FK; added `FrameworkDescriptor` for Generic Attributes; resolved all audit findings; added schema migration script |
| 2026-04-30 | Initial Phase 5 Draft | Architecture and deliverables outline |
