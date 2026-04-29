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

⚠️ **Version Bump Required**: This phase introduces a new Prisma migration (`FrameworkDescriptor` and `FrameworkScoringRubric` models) and an optional embedding dimension config. **Before implementation begins**, run:

```bash
/bump-version
```

Choose a MINOR bump (e.g., v0.6.0 → v0.7.0). Then create the migration:

```bash
cd packages/database
pnpm prisma migrate dev --name v0_7_0_add_framework_config_and_skill_embeddings
```

## Objective

Establish a tiered prompt architecture with Claude's native caching and dynamic RAG injection:

1. **Static system prompt** (cached by Claude): Framework-agnostic assessor behavioral rubric + Generic Attributes definitions per framework
2. **Dynamic RAG context** (per turn, injected into Pipecat task_messages): Skill definitions retrieved in real time from pgvector
3. **SFIA 9 data ingestion**: Extract skill definitions and attributes from the official SFIA 9 Excel file, store embeddings, and pre-populate the assessment system

---

## 1. Deliverables

### 1.1 Database Schema — Framework Configuration Tables

Add two new Prisma models to `packages/database/prisma/schema.prisma`:

#### 1.1.1 FrameworkDescriptor

Stores framework-agnostic structure (Generic Attributes definitions for each level):

```prisma
/// Generic Attributes framework (Autonomy, Influence, Complexity, etc.)
/// with level-specific descriptors (1-7). Used to populate the static cached
/// system prompt during assessment initialization.
model FrameworkDescriptor {
  id                String   @id @default(uuid())
  frameworkType     String   @db.VarChar(50)      // e.g., "sfia-9", "togaf"
  frameworkVersion  String   @db.VarChar(20)      // e.g., "9.0"
  attribute         String   @db.VarChar(100)     // e.g., "Autonomy", "Influence"
  level             Int                            // 1-7
  description       String                         // Multi-sentence descriptor
  createdAt         DateTime @default(now())

  @@unique([frameworkType, frameworkVersion, attribute, level])
  @@index([frameworkType])
  @@index([frameworkType, frameworkVersion])
  @@map("framework_descriptors")
}
```

#### 1.1.2 FrameworkScoringRubric

Stores the assessor's behavioral scoring guide per framework (cached in system prompt):

```prisma
/// Assessor behavioral scoring rubric: guidance for the LLM on how to score
/// responsibility levels (1-7) for each attribute. Framework-specific.
/// Injected into the static system prompt to ensure consistent scoring across all calls.
model FrameworkScoringRubric {
  id                String   @id @default(uuid())
  frameworkType     String   @db.VarChar(50)
  frameworkVersion  String   @db.VarChar(20)
  rubric            String                         // Long-form text: scoring guidance
  createdAt         DateTime @default(now())
  updatedAt         DateTime @updatedAt

  @@unique([frameworkType, frameworkVersion])
  @@index([frameworkType])
  @@map("framework_scoring_rubrics")
}
```

**Notes:**
- The `rubric` field stores the full assessor guidance (typically 200-500 words per framework).
- For SFIA 9, this includes the scoring interpretation for Autonomy, Influence, Complexity, Business Skills, and Knowledge attributes.
- Framework-agnostic: swap the rubric without schema changes.
- The rubric is loaded into the static system prompt once per call initialization (see section 1.7).

### 1.2 Ports: IEmbeddingService & IKnowledgeBase

Define two ports in `apps/voice-engine/src/domain/ports/`:

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

### 1.3 Database Schema — SkillEmbedding Table

**Update** `packages/database/prisma/schema.prisma` — the `SkillEmbedding` model already exists from Phase 3, but clarify field naming:

```prisma
/// Vector store for framework skill definitions (SFIA 9, TOGAF, etc.).
/// One row per (framework, skill, level) combination.
/// The `embedding` column is Unsupported because Prisma lacks native pgvector support;
/// queries use raw SQL. See section 1.6 for raw SQL index creation.
model SkillEmbedding {
  id               String   @id @default(uuid())
  frameworkType    String   @db.VarChar(50)
  frameworkVersion String   @db.VarChar(20)
  skillCode        String   @db.VarChar(50)
  skillName        String   @db.VarChar(255)
  category         String   @db.VarChar(100)
  subcategory      String?  @db.VarChar(100)
  level            Int?                          // 1-7; NULL for skill summary
  content          String                        // Chunked text for embedding
  embedding        Unsupported("vector(1536)")? // OpenAI text-embedding-3-small
  metadata         Json     @default("{}")       // Extensible data (e.g., keywords)
  createdAt        DateTime @default(now())

  @@unique([frameworkType, frameworkVersion, skillCode, level], name: "idx_unique_framework_skill_level")
  @@index([frameworkType])
  @@index([skillCode])
  @@map("skill_embeddings")
}
```

**Migration note**: If the table doesn't exist from Phase 3, the `prisma migrate dev` command above will create it.

### 1.4 pgvector Index Creation

**Post-migration**, create the IVFFlat index for efficient vector similarity search. Run this **once** against the production database:

```sql
-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create IVFFlat index for approximate nearest-neighbor search
CREATE INDEX idx_skill_embeddings_embedding
    ON skill_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Create a covering index for framework + skill lookups
CREATE INDEX idx_skill_embeddings_framework_skill
    ON skill_embeddings (framework_type, framework_version, skill_code);
```

**Note**: After bulk ingestion or re-ingestion, run `REINDEX idx_skill_embeddings_embedding;` to maintain index quality.

### 1.5 SFIA 9 Data Extraction & Ingestion

**Source**: The official SFIA 9 Excel file at `docs/development/contracts/sfia-9.xlsx` contains four worksheets:
- **Skills**: Skill code, name, category, subcategory, and level descriptions (1-7)
- **Attributes**: Generic Attributes (Autonomy, Influence, Complexity, Business Skills, Knowledge) with level-specific text
- **Levels of responsibility**: Detailed guidance for each level (1-7)
- **Read Me Notes**: Licensing and copyright

#### 1.5.1 Extract Framework Attributes

**File:** `apps/voice-engine/src/scripts/extract_sfia_attributes.py`

Extracts the four Generic Attributes from the SFIA Excel "Attributes" sheet and populates `FrameworkDescriptor` table:

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
    Extract SFIA 9 Generic Attributes from Excel and populate FrameworkDescriptor.
    
    SFIA defines 5 attributes: Autonomy, Influence, Complexity, Business Skills, Knowledge.
    Each has 7-level descriptors.
    """
    wb = openpyxl.load_workbook(excel_path)
    attributes_sheet = wb["Attributes"]
    
    # Parse worksheet (assumes format: attribute name in col A, level 1 desc in col B, level 2 in col C, etc.)
    rows_inserted = 0
    
    async with db_pool.acquire() as conn:
        for row in attributes_sheet.iter_rows(min_row=2):  # Skip header
            attribute = row[0].value  # e.g., "Autonomy"
            
            for level in range(1, 8):
                description = row[level].value  # Columns B-H = levels 1-7
                if not description:
                    continue
                
                await conn.execute(
                    """
                    INSERT INTO framework_descriptors 
                        (framework_type, framework_version, attribute, level, description)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT DO NOTHING
                    """,
                    framework_type, framework_version, attribute, level, description,
                )
                rows_inserted += 1
    
    print(f"Extracted {rows_inserted} attribute descriptors for {framework_type}")
```

#### 1.5.2 Extract and Ingest SFIA Skills

**File:** `apps/voice-engine/src/scripts/ingest_sfia_skills.py`

Extracts skill definitions from the SFIA Excel "Skills" sheet, generates embeddings, and upserts into `skill_embeddings`:

```python
import openpyxl
import asyncpg
from typing import Any
from domain.ports.embedding_service import IEmbeddingService

async def ingest_sfia_skills(
    excel_path: str,
    db_pool: asyncpg.Pool,
    embedder: IEmbeddingService,
    framework_type: str = "sfia-9",
    framework_version: str = "9.0",
):
    """
    Extract SFIA skills from Excel, compose chunks, generate embeddings, and upsert.
    
    Expected columns in 'Skills' sheet:
    - Code, URL, Skill, Category, Subcategory, Overall description, Guidance notes
    - Level 1 description, Level 2 description, ..., Level 7 description
    """
    wb = openpyxl.load_workbook(excel_path)
    skills_sheet = wb["Skills"]
    
    chunks_ingested = 0
    failed = 0
    
    async with db_pool.acquire() as conn:
        for row in skills_sheet.iter_rows(min_row=2, values_only=True):
            try:
                skill_code, _, skill_name, category, subcategory, *descriptions = row
                
                # Descriptions: [overall, guidance, level 1, level 2, ..., level 7]
                overall_desc = descriptions[0] or ""
                guidance = descriptions[1] or ""
                level_descriptions = descriptions[2:9]  # 7 levels
                
                for level, level_desc in enumerate(level_descriptions, start=1):
                    if not level_desc:
                        continue
                    
                    # Compose chunk with overall context + level-specific descriptor
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
                    
                    # Generate embedding
                    embedding = await embedder.embed(content)
                    
                    # Upsert into skill_embeddings
                    await conn.execute(
                        """
                        INSERT INTO skill_embeddings 
                            (framework_type, framework_version, skill_code, skill_name,
                             category, subcategory, level, content, embedding, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (framework_type, framework_version, skill_code, level)
                        DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            skill_name = EXCLUDED.skill_name
                        """,
                        framework_type, framework_version, skill_code, skill_name,
                        category, subcategory, level, content, embedding, "{}",
                    )
                    chunks_ingested += 1
            
            except Exception as e:
                print(f"Error ingesting skill {row[0]}: {e}")
                failed += 1
    
    print(f"Ingested {chunks_ingested} skill-level chunks ({failed} failed)")
```

**Ingestion instructions**:
1. Run extract_sfia_attributes.py first (populates framework descriptors)
2. Run ingest_sfia_skills.py (upserts skills and embeddings)
3. Expected result: ~500-800 chunks for SFIA 9 (120 skills × varying levels)
```

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

Implements the `IKnowledgeBase` port using PostgreSQL pgvector:

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
        
        conditions = ["framework_type = $2"]
        params = [embedding, framework_type]
        param_idx = 3
        
        if level_filter is not None:
            conditions.append(f"level = ${param_idx}")
            params.append(level_filter)
            param_idx += 1
        
        if skill_codes:
            conditions.append(f"skill_code = ANY(${param_idx}::text[])")
            params.append(skill_codes)
            param_idx += 1
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT id, framework_type, skill_code, skill_name, category,
                   subcategory, level, content,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM skill_embeddings
            WHERE {where_clause}
            ORDER BY embedding <=> $1::vector
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
            SELECT id, framework_type, skill_code, skill_name, category,
                   subcategory, level, content
            FROM skill_embeddings
            WHERE framework_type = $1 AND skill_code = $2
            ORDER BY level ASC
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

Constructs the static, cacheable system prompt that includes bot persona, assessor rubric, and Generic Attributes definitions. This prompt is cached by Claude and reused across turns:

```python
from domain.ports.knowledge_base import IKnowledgeBase

class SystemPromptBuilder:
    """Builds the static system prompt for caching by Claude."""
    
    def __init__(self, knowledge_base: IKnowledgeBase):
        self.knowledge_base = knowledge_base
    
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
        # Fetch assessor behavioral scoring rubric
        rubric = await self._fetch_scoring_rubric(framework_type, framework_version)
        
        # Fetch Generic Attributes definitions (all 7 levels)
        attributes_text = await self._build_attributes_section(framework_type, framework_version)
        
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

## SFIA Generic Attributes Reference

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

Never quote SFIA codes to the candidate. Always translate framework concepts into natural language.
"""
    
    async def _fetch_scoring_rubric(self, framework_type: str, framework_version: str) -> str:
        """Fetch the assessor behavioral scoring rubric from database."""
        # TODO: Query FrameworkScoringRubric table
        # For now, return a template for SFIA
        return (
            "Score candidates on a scale of 1-7 based on demonstrated autonomy, influence, "
            "complexity handling, and knowledge depth. Level 1: awareness, following direction. "
            "Level 7: strategic leadership, organizational impact."
        )
    
    async def _build_attributes_section(self, framework_type: str, framework_version: str) -> str:
        """Fetch Generic Attributes and format for system prompt."""
        # TODO: Query FrameworkDescriptor table
        # Build a formatted section with all 5 attributes × 7 levels
        return (
            "### Autonomy\n"
            "Level 1-2: Works under routine direction, needs guidance.\n"
            "Level 3-4: Works with some independence, follows established patterns.\n"
            "Level 5-6: Designs solutions, sets direction within scope.\n"
            "Level 7: Sets organizational strategy and direction.\n\n"
            "### Influence\n"
            "Level 1-2: Interacts with immediate team.\n"
            "Level 3-4: Influences peers and cross-functional teams.\n"
            "Level 5-6: Influences organizational decisions.\n"
            "Level 7: Sets strategic direction across organization.\n"
            # ... (similar for Complexity, Business Skills, Knowledge)
        )
```

### 1.9 Dynamic RAG Context Injector for Pipecat

**File:** `apps/voice-engine/src/flows/rag_context_injector.py`

Injects RAG-retrieved skill context into Pipecat's `task_messages` **before each LLM call**. This component is called by `SfiaFlowController` after receiving user input:

```python
from domain.ports.knowledge_base import IKnowledgeBase, SkillDefinition

class RAGContextInjector:
    """
    Manages dynamic RAG context injection into Pipecat task_messages.
    
    The static system prompt (cached) is separate; this handles per-turn
    context updates during skill_discovery and evidence_gathering phases.
    """
    
    def __init__(self, knowledge_base: IKnowledgeBase):
        self.knowledge_base = knowledge_base
        self._identified_skills: list[str] = []
    
    async def inject_context_for_turn(
        self,
        user_text: str,
        current_phase: str,
        framework_type: str = "sfia-9",
    ) -> str:
        """
        Retrieve RAG context and return as a formatted string to append
        to the current task_messages before calling the LLM.
        
        Returns:
            A string with RAG context, or empty string if no context needed.
        """
        # Only inject during these phases
        if current_phase not in ("skill_discovery", "evidence_gathering"):
            return ""
        
        # Determine query strategy
        if current_phase == "evidence_gathering" and self._identified_skills:
            results = await self.knowledge_base.query(
                text=user_text,
                framework_type=framework_type,
                skill_codes=self._identified_skills,
                top_k=3,  # Focused: top 3 related to identified skills
            )
        elif current_phase == "skill_discovery":
            results = await self.knowledge_base.query(
                text=user_text,
                framework_type=framework_type,
                top_k=5,  # Broader: top 5 across all skills
            )
        else:
            return ""
        
        # Format results
        if not results:
            return ""
        
        return self._format_rag_context(results)
    
    def set_identified_skills(self, skill_codes: list[str]) -> None:
        """Called when SfiaFlowController.handle_skills_identified() fires."""
        self._identified_skills = skill_codes
    
    def _format_rag_context(self, results: list[SkillDefinition]) -> str:
        """Format retrieved skills for insertion into task_messages."""
        lines = [">>> RAG CONTEXT START"]
        
        for skill in results:
            lines.append(f"\n**{skill.skill_name} ({skill.skill_code}) - Level {skill.level}**")
            lines.append(f"[Relevance: {skill.similarity:.1%}]")
            lines.append(f"\n{skill.content}")
        
        lines.append("\n>>> RAG CONTEXT END")
        return "\n".join(lines)
```

**Integration with SfiaFlowController**: Modify `apps/voice-engine/src/flows/sfia_flow_controller.py` to call `RAGContextInjector` before each node's LLM execution:

```python
# In _build_skill_discovery_node():
rag_context = await self._rag_injector.inject_context_for_turn(
    user_text=<captured from last user turn>,
    current_phase="skill_discovery",
)

# Append to task_messages:
task_messages = [
    { "role": "user", "content": "Ask about main skills..." },
]
if rag_context:
    task_messages.insert(0, { "role": "system", "content": rag_context })
```

---

## 2. Framework Configuration & SFIA 9 Initialization

### SFIA 9 Data Source

The official SFIA 9 Excel file is located at `docs/development/contracts/sfia-9.xlsx`. It contains:

| Sheet | Content | Usage |
|-------|---------|-------|
| **Skills** | Skill codes, names, categories, level descriptions (1-7) | Ingest into `skill_embeddings` |
| **Attributes** | Generic Attributes (Autonomy, Influence, Complexity, Business Skills, Knowledge) with level-specific text | Populate `FrameworkDescriptor` |
| **Levels of responsibility** | Detailed guidance for responsibility levels 1-7 | Reference for assessor rubric |
| **Read Me Notes** | Licensing, copyright, usage terms | Compliance verification |

### SFIA 9 Pre-Load Process

Before deployment, run the two ingestion scripts in order:

```bash
# 1. Extract Generic Attributes into FrameworkDescriptor table
python apps/voice-engine/src/scripts/extract_sfia_attributes.py \
  --excel docs/development/contracts/sfia-9.xlsx \
  --framework-type sfia-9 \
  --framework-version 9.0

# 2. Ingest skills and generate embeddings
python apps/voice-engine/src/scripts/ingest_sfia_skills.py \
  --excel docs/development/contracts/sfia-9.xlsx \
  --framework-type sfia-9 \
  --framework-version 9.0
```

**Expected result**: 
- ~85-95 rows in `FrameworkDescriptor` (5 attributes × 7 levels, plus summary rows)
- ~500-800 chunks in `skill_embeddings` (120 skills × varying levels)

### Framework Scoring Rubric Setup

Post-ingestion, populate the `FrameworkScoringRubric` table with the assessor guidance. For SFIA 9, this includes interpretation of the Generic Attributes and scoring guidelines:

```bash
python apps/voice-engine/src/scripts/load_sfia_rubric.py \
  --framework-type sfia-9 \
  --rubric-file docs/development/scoring-rubrics/sfia-9-rubric.txt
```

**Contents of sfia-9-rubric.txt** (to be created):
```
SFIA 9 Assessment Rubric — Autonomy, Influence, Complexity, Business Skills, Knowledge

Scoring Guidelines:
- Level 1-2: Foundation competence, works under routine direction
- Level 3-4: Practitioner, works with some independence
- Level 5-6: Expert, sets direction, influences others
- Level 7: Strategic, shapes organizational capability

Evidence Scoring:
- Listen for concrete examples of autonomy (decision-making), influence (impact on others),
  complexity (ambiguity, scale, technical depth), and knowledge (depth, breadth, innovation).
- Map evidence to SFIA skill definitions provided via RAG context.
- Assign level 1-7 based on demonstrated attributes.
```

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

#### Layer 2: Dynamic RAG Context (Pipecat task_messages)

Updated on every user turn during `skill_discovery` and `evidence_gathering`:

```
PER-TURN PIPECAT CONTEXT:
├─ task_messages:
│  ├─ [system]: ">>> RAG CONTEXT START\n{retrieved skill definitions}\n>>> RAG CONTEXT END"
│  └─ [user]: "{phase-specific instruction}"
└─ history: [all previous turns in conversation]
```

When `RAGContextInjector.inject_context_for_turn()` is called, it retrieves relevant skills and prepends a system message to `task_messages`.

### Call Flow with Tiered Architecture

```
┌─ CALL STARTS ─────────────────────────────┐
│ 1. Create AssessmentSession               │
│ 2. Load framework config (sfia-9)         │
│ 3. Build static system prompt             │
│    - Fetch FrameworkScoringRubric         │
│    - Fetch FrameworkDescriptor (all levels) │
│    - Compose into SystemPromptBuilder     │
│                                            │
│ 4. Initialize Pipecat pipeline            │
│    - Set system prompt (this is cached)   │
│    - Initialize SfiaFlowController        │
│    - Initialize RAGContextInjector        │
└────────────────────────────────────────────┘
           ↓
┌─ FOR EACH TURN ───────────────────────────┐
│ 1. Candidate speaks                       │
│ 2. STT captures: "I've worked on Docker"  │
│ 3. Check current phase (e.g., skill_discovery)
│ 4. If skill_discovery or evidence_gathering:
│    - Call RAGContextInjector.inject_context_for_turn()
│    - Retrieve pgvector results (e.g., top 5 skills) │
│    - Format as ">>> RAG CONTEXT START..."           │
│    - Prepend to task_messages                       │
│ 5. Call Claude with:                     │
│    - system: [cached prompt]             │
│    - messages: [history + RAG context]   │
│ 6. Claude generates response              │
│ 7. TTS plays response                     │
│                                            │
│ (For introduction, summary, closing:      │
│  Skip step 4 — use fixed task_messages)  │
└────────────────────────────────────────────┘
```

### Latency Targets

| Component | Latency | Notes |
|-----------|---------|-------|
| pgvector query | < 10ms | IVFFlat index, ~800 embeddings |
| Embedding API call (single text) | ~100-200ms | OpenAI text-embedding-3-small |
| RAG formatting & injection | < 5ms | String manipulation |
| **Total RAG overhead per turn** | **~150-250ms** | Acceptable for natural conversation (~2-3s between turns) |
| Claude API call (with caching) | ~200-500ms | Cached system prompt reduces token cost |

**Cache efficiency**: After the first turn, Claude's cache hit reduces input tokens by ~90% for the static system prompt, reducing both latency and cost.

### Context Update Frequency

| Phase | RAG Behavior |
|-------|--------------|
| **introduction** | No RAG queries; fixed system prompt only |
| **skill_discovery** | RAG query on every user turn; broad search (top 5) |
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

- [ ] `FrameworkDescriptor` table created with columns: `id`, `frameworkType`, `frameworkVersion`, `attribute`, `level`, `description`
- [ ] `FrameworkScoringRubric` table created with columns: `id`, `frameworkType`, `frameworkVersion`, `rubric` (long text)
- [ ] `SkillEmbedding` table exists with `embedding` column as `vector(1536)`
- [ ] pgvector extension enabled; raw SQL migration runs without errors
- [ ] IVFFlat index created on `skill_embeddings.embedding` with `lists = 100`
- [ ] Extract SFIA attributes script populates `FrameworkDescriptor` with 35 rows (5 attributes × 7 levels)
- [ ] Ingest SFIA skills script populates `skill_embeddings` with 500–800 chunks (verified row count)
- [ ] Ingestion is idempotent: re-running does not duplicate rows (ON CONFLICT updated, not inserted)

### Port & Adapter Implementation

- [ ] `IEmbeddingService` port defined with `embed(text)` and `embed_batch(texts)` methods
- [ ] `IKnowledgeBase` port defined with `query()` and `query_by_skill_code()` methods
- [ ] `OpenAIEmbeddingService` adapter implements `IEmbeddingService`; uses `text-embedding-3-small` (1536 dims)
- [ ] `PgVectorKnowledgeBase` adapter implements `IKnowledgeBase`; queries pgvector and returns `SkillDefinition` objects
- [ ] Both adapters are dependency-injected (not hardcoded in core logic)

### Static Prompt Architecture (Claude Caching)

- [ ] `SystemPromptBuilder.build_cached_system_prompt()` successfully fetches `FrameworkScoringRubric` and `FrameworkDescriptor`
- [ ] Built prompt includes bot persona, rubric, and Generic Attributes (5 attrs × 7 levels)
- [ ] Prompt is marked for caching in Pipecat context (passed to Claude as system message)
- [ ] Cached prompt is reused across all turns in a single call (verified via prompt cache metrics)

### Dynamic RAG Context Injection

- [ ] `RAGContextInjector.inject_context_for_turn()` queries pgvector during `skill_discovery` phase
- [ ] RAG query uses broad search strategy in `skill_discovery`: `top_k=5`, no skill filters
- [ ] RAG query uses focused strategy in `evidence_gathering`: `top_k=3`, filtered by `skill_codes`
- [ ] RAG context formatted with ">>> RAG CONTEXT START / END" markers
- [ ] RAG context is inserted as a system message into `task_messages` before LLM call
- [ ] No RAG queries during `introduction`, `summary`, `closing` phases
- [ ] If `SkillEmbedding` table is empty, RAG context gracefully returns empty string (fallback behavior)

### Integration & Latency

- [ ] End-to-end test: user text → embedding → pgvector query → formatted context → LLM response
- [ ] P95 latency for single RAG query (embedding + pgvector lookup) ≤ 250ms in production database (measured)
- [ ] Debouncing: multiple rapid utterances batch into single RAG query (verified with timing logs)
- [ ] Claude's prompt caching working: verify `cache_creation_input_tokens` and `cache_read_input_tokens` in API response (first turn creates cache, subsequent turns read from cache)
- [ ] Integration with `SfiaFlowController`: `handle_skills_identified()` correctly updates `RAGContextInjector._identified_skills`

### Extensibility

- [ ] Adding a new framework (e.g., TOGAF) requires only data (Excel file + ingestion script), no schema changes
- [ ] Query with `framework_type="togaf"` returns TOGAF results; `framework_type="sfia-9"` returns SFIA results
- [ ] `FrameworkScoringRubric` can be updated without redeploying code (long text field)

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

1. ✅ Run Prisma migration to create `FrameworkDescriptor` and `FrameworkScoringRubric` tables
2. ✅ Create pgvector indexes via raw SQL
3. ✅ Verify `docs/development/contracts/sfia-9.xlsx` is available and licensing confirmed
4. ✅ Run extraction script: `extract_sfia_attributes.py`
5. ✅ Run ingestion script: `ingest_sfia_skills.py`
6. ✅ Load assessor rubric: `load_sfia_rubric.py`
7. ✅ Deploy updated `sfia_flow_controller.py` with `RAGContextInjector` integration
8. ✅ Run integration tests against production database (no real calls)
9. ✅ Monitor first 10 live calls for latency and prompt cache hit rate
10. ✅ Document any schema tweaks or configuration changes in runbook

### Revision History

| Date | Change | Notes |
|------|--------|-------|
| 2026-04-30 | Refine Phase 5 | Implemented tiered prompt strategy with Claude caching + dynamic RAG; added framework configuration tables; corrected field naming (frameworkVersion); resolved high-priority audit findings |
