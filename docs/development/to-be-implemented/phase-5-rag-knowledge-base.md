# Phase 5: RAG Knowledge Base & SFIA Data Ingestion

## Status
To Be Implemented

## Date
2026-04-18

## References
- PRD-002: Assessment Interview Workflow
- ADR-005: RAG & Vector Store Strategy
- Phase 1: Foundation & Monorepo Scaffold (prerequisite — defines Prisma schema)
- Phase 2: Basic Voice Engine & Call Tracking (prerequisite)
- Phase 3: Infrastructure Deployment (prerequisite)
- Phase 4: Assessment Workflow & Interjection (prerequisite for runtime integration)

## Objective

Set up the pgvector-based knowledge base, ingest SFIA 9 skill definitions with framework-type metadata, implement the `SkillRetriever` class, and wire RAG context into the Pipecat pipeline's system prompt during live calls.

---

## 1. Deliverables

### 1.1 KnowledgeBase Port Definition

**File:** `apps/voice-engine/src/domain/ports/knowledge_base.py`

The `IKnowledgeBase` port is deferred from Phase 1 and defined here:

```python
from abc import ABC, abstractmethod
from domain.models.skill import SkillDefinition

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
            framework_type: Which framework to search (default: sfia-9)
            top_k: Number of results to return
            level_filter: Restrict results to a specific responsibility level (1-7)
            skill_codes: Restrict to specific skill codes (for targeted probing)

        Returns:
            List of matching SkillDefinition objects ordered by relevance
        """
        ...
```

### 1.2 pgvector Schema & Migration

**Update to Prisma schema:** In `packages/database/prisma/schema.prisma`, add the `SkillEmbedding` model:

```prisma
model SkillEmbedding {
  id                String   @id @default(uuid())
  frameworkType     String   @db.VarChar(50)  // e.g., "sfia-9"
  frameworkVersion  String   @db.VarChar(20)  // e.g., "9.0"
  skillCode         String   @db.VarChar(50)  // e.g., "INFL"
  skillName         String   @db.VarChar(255)
  category          String   @db.VarChar(100)
  subcategory       String?  @db.VarChar(100)
  level             Int?                       // 1-7 for SFIA
  content           String   @db.Text         // The chunked text for embedding
  embedding         Unsupported("vector(1536)")?  // pgvector embeddings
  metadata          Json?
  createdAt         DateTime @default(now())

  @@unique([frameworkType, frameworkVersion, skillCode, level], name: "idx_unique_framework_skill_level")
  @@index([frameworkType, frameworkVersion])
  @@index([skillCode])
  @@index([frameworkType])
}
```

**Notes:**
- `embedding` uses `Unsupported("vector(1536)")` because Prisma doesn't have native pgvector support yet. Raw SQL or a migration file will handle this.
- The unique constraint ensures no duplicate (framework, skill, level) combinations.
- Post-migration, add the IVFFlat index manually via raw SQL:

```sql
-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create IVFFlat index for efficient similarity search
CREATE INDEX idx_skill_embeddings_embedding
    ON skill_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

### 1.3 SFIA 9 Data Ingestion Pipeline

**File:** `apps/voice-engine/src/scripts/ingest_sfia.py`

A one-time (re-runnable) script that:
1. Reads SFIA 9 skill definitions from a structured source (JSON/CSV).
2. Composes the text chunk for each (skill, level) combination.
3. Generates embeddings via OpenAI `text-embedding-3-small`.
4. Upserts into the `skill_embeddings` table with `framework_type = "sfia-9"`.

**Chunk composition template:**

```python
def compose_chunk(skill: SFIASkillData, level: SFIALevelData) -> str:
    """Compose a text chunk for embedding."""
    return (
        f"Framework: SFIA 9\n"
        f"Skill: {skill.name} ({skill.code})\n"
        f"Category: {skill.category}"
        f"{f' > {skill.subcategory}' if skill.subcategory else ''}\n"
        f"Level: {level.level}\n\n"
        f"Description:\n{level.description}\n\n"
        f"Autonomy: {level.autonomy}\n"
        f"Influence: {level.influence}\n"
        f"Complexity: {level.complexity}\n"
        f"Knowledge: {level.knowledge}\n"
    )
```

**Ingestion flow:**

```python
async def ingest_sfia_skills(
    source_path: str,
    db: AsyncConnection,
    embedder: EmbeddingService,
    framework_type: str = "sfia-9",
    framework_version: str = "9.0",
):
    skills = load_sfia_source(source_path)
    
    for skill in skills:
        for level in skill.levels:
            content = compose_chunk(skill, level)
            embedding = await embedder.embed(content)
            
            await db.execute(
                """
                INSERT INTO skill_embeddings 
                    (framework_type, framework_ver, skill_code, skill_name,
                     category, subcategory, level, content, embedding, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (framework_type, framework_ver, skill_code, level)
                DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    skill_name = EXCLUDED.skill_name,
                    metadata = EXCLUDED.metadata
                """,
                framework_type, framework_version, skill.code, skill.name,
                skill.category, skill.subcategory, level.level, content,
                embedding, json.dumps(skill.metadata),
            )
    
    print(f"Ingested {sum(len(s.levels) for s in skills)} chunks for {framework_type}")
```

### 1.4 PgVectorKnowledgeBase Adapter

**File:** `apps/voice-engine/src/adapters/pgvector_knowledge_base.py`

Implements the `IKnowledgeBase` port using pgvector.

```python
from domain.ports.knowledge_base import KnowledgeBase
from domain.models.skill import SkillDefinition

class PgVectorKnowledgeBase(KnowledgeBase):
    def __init__(self, db_pool: asyncpg.Pool, embedder: EmbeddingService):
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
        """
        Query the vector store for skill definitions relevant to the given text.
        
        Supports filtering by:
        - framework_type: Which framework to search (default: sfia-9)
        - level_filter: Specific responsibility level (1-7)
        - skill_codes: Restrict to specific skill codes (for targeted probing)
        """
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
        """Retrieve all levels for a specific skill (no vector search, direct lookup)."""
        query = """
            SELECT id, framework_type, skill_code, skill_name, category,
                   subcategory, level, content
            FROM skill_embeddings
            WHERE framework_type = $1 AND skill_code = $2
            ORDER BY level ASC
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, framework_type, skill_code)
            return [SkillDefinition.from_row(row) for row in rows]
```

### 1.4 Dynamic System Prompt Injection

**File:** `apps/voice-engine/src/flows/rag_prompt_injector.py`

This component sits between the user's speech and the LLM, enriching the system prompt with retrieved SFIA context.

```python
class RAGPromptInjector:
    """
    Dynamically updates the LLM system prompt with RAG-retrieved
    SFIA skill definitions based on what the candidate is discussing.
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base
        self._current_context: list[SkillDefinition] = []
        self._identified_skills: list[str] = []

    async def update_context(
        self,
        user_text: str,
        current_state: str,
        context: OpenAILLMContext,
    ) -> None:
        """
        Called after each user turn. Retrieves relevant skills and
        updates the system prompt with fresh RAG context.
        """
        if current_state == "evidence_gathering":
            # During evidence gathering, focus on identified skills
            results = await self.knowledge_base.query(
                text=user_text,
                skill_codes=self._identified_skills,
                top_k=3,
            )
        elif current_state == "skill_discovery":
            # During discovery, cast a wider net
            results = await self.knowledge_base.query(
                text=user_text,
                top_k=5,
            )
        else:
            return

        self._current_context = results
        self._inject_into_prompt(context)

    def set_identified_skills(self, skill_codes: list[str]):
        """Called when SkillDiscovery identifies candidate's skills."""
        self._identified_skills = skill_codes

    def _inject_into_prompt(self, context: OpenAILLMContext):
        """Replace the RAG context placeholder in the system prompt."""
        rag_text = self._format_context()
        
        for msg in context.messages:
            if msg["role"] == "system" and "{rag_context}" in msg["content"]:
                msg["content"] = msg["content"].replace("{rag_context}", rag_text)
                break

    def _format_context(self) -> str:
        if not self._current_context:
            return "No specific SFIA skills matched yet. Continue asking about the candidate's experience."
        
        sections = []
        for skill in self._current_context:
            sections.append(
                f"--- {skill.skill_name} ({skill.skill_code}) - Level {skill.level} ---\n"
                f"{skill.content}\n"
                f"[Relevance: {skill.similarity:.2f}]"
            )
        
        return "\n\n".join(sections)
```

### 1.5 Embedding Service Adapter

**File:** `apps/voice-engine/src/adapters/openai_embedder.py`

```python
from openai import AsyncOpenAI

class OpenAIEmbeddingService:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def embed(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            input=text,
            model=self.model,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            input=texts,
            model=self.model,
        )
        return [item.embedding for item in response.data]
```

---

## 2. SFIA 9 Data Source

### Source Format

SFIA 9 skill definitions should be provided as structured JSON:

```json
{
  "framework": "sfia-9",
  "version": "9.0",
  "skills": [
    {
      "code": "PROG",
      "name": "Programming/Software Development",
      "category": "Development and implementation",
      "subcategory": "Software design",
      "levels": [
        {
          "level": 2,
          "description": "Designs, codes, verifies, tests, documents...",
          "autonomy": "Works under routine direction...",
          "influence": "Interacts with and may influence immediate colleagues...",
          "complexity": "Performs a range of work activities in varied environments...",
          "knowledge": "Has gained a basic domain knowledge..."
        }
      ]
    }
  ]
}
```

### Data Preparation Notes

- SFIA 9 has approximately 120 skills across 6 categories and 19 subcategories.
- Not all skills have all 7 levels (some start at level 2 or 3).
- Expected total chunks: ~500-800 (skill-level combinations).
- The `metadata` JSONB field can store additional attributes (e.g., related skills, keywords).

### Pluggability for Future Frameworks

To add a new framework (e.g., TOGAF):
1. Prepare a JSON file in the same structure with `framework: "togaf"`.
2. Run the ingestion script with `--framework-type togaf --framework-version 10.0`.
3. Query with `framework_type="togaf"` in the `SkillRetriever`.
4. No schema changes, no code changes — only data.

---

## 3. Runtime Integration with Voice Pipeline

### Sequence Diagram

```
Candidate speaks → STT → User text
                            │
                            ▼
                   RAGPromptInjector.update_context()
                            │
                            ├─── query pgvector for relevant skills
                            │
                            ├─── update system prompt with context
                            │
                            ▼
                   LLM generates response (now SFIA-informed)
                            │
                            ▼
                   TTS → Audio to candidate
```

### Context Update Frequency

- Context is updated on every user turn during `skill_discovery` and `evidence_gathering` states.
- During `introduction`, `summary`, and `closing`, no RAG queries are made (fixed prompts).
- Debouncing: If the user speaks multiple short utterances in quick succession, batch them into a single query.

### Latency Considerations

- pgvector query (IVFFlat, ~800 rows): < 10ms
- Embedding API call: ~100-200ms
- Total RAG overhead per turn: ~150-250ms (acceptable for conversational cadence)

---

## 4. Acceptance Criteria

- [ ] pgvector extension is enabled in PostgreSQL.
- [ ] `skill_embeddings` table is created with all columns and indexes.
- [ ] SFIA 9 ingestion script runs successfully and populates the table.
- [ ] `PgVectorKnowledgeBase.query()` returns relevant results with similarity scores.
- [ ] `PgVectorKnowledgeBase.query()` filters correctly by `framework_type`.
- [ ] `PgVectorKnowledgeBase.query()` filters correctly by `level` and `skill_codes`.
- [ ] `PgVectorKnowledgeBase.query_by_skill_code()` returns all levels for a skill.
- [ ] `RAGPromptInjector` updates the system prompt with retrieved context.
- [ ] `RAGPromptInjector` uses different query strategies per conversation state.
- [ ] Integration test: user speech → RAG query → enriched LLM prompt → relevant response.
- [ ] Ingestion is idempotent (re-running does not duplicate data).
- [ ] Latency of RAG query + embedding < 300ms (measured).

## 5. Dependencies

- **Phase 1**: Database schema, port interfaces.
- **Phase 2**: Basic voice infrastructure, call tracking.
- **Phase 3**: Infrastructure deployed to production.
- **Phase 4**: Assessment workflow state machine (for runtime integration).
- **External**: OpenAI API key (for embeddings), PostgreSQL with pgvector.

## 6. Risks

| Risk | Mitigation |
|------|------------|
| SFIA skill definitions not freely available | Verify licensing; fallback to manually curated subset |
| Embedding quality for technical competency text | Test with sample queries; consider domain-specific fine-tuning |
| pgvector IVFFlat index staleness after re-ingestion | Run `REINDEX` after bulk ingestion; document in runbook |
| OpenAI embedding API rate limits during batch ingestion | Implement backoff; batch embedding calls (max 2048 per request) |
