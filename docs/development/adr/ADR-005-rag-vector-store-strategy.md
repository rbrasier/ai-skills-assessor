# ADR-005: RAG & Vector Store Strategy (pgvector, Framework-Type Metadata)

## Status
Accepted

## Date
2026-04-16

## Context

The Voice-AI assessment bot must dynamically retrieve SFIA 9 skill definitions and responsibility level descriptions during a live call. As the candidate mentions skills, experiences, or domains, the bot needs to:
1. Identify which SFIA skills are relevant to what the candidate just said.
2. Retrieve the full skill definition and level descriptors (Levels 1–7) for those skills.
3. Inject this context into the LLM system prompt so the bot can ask informed, level-appropriate probing questions.

Additionally, the architecture must support future frameworks beyond SFIA (e.g., TOGAF, ITIL, PMBOK) without requiring schema changes or re-architecture.

## Options Considered

### Vector Store

| Option | Strengths | Weaknesses |
|--------|-----------|------------|
| **pgvector (PostgreSQL extension)** | Same database as application data; no new infra; good enough for our scale; SQL-based filtering | Not as performant as dedicated vector DBs at massive scale |
| **Pinecone** | Managed service; excellent performance; metadata filtering | Additional vendor; separate infra; cost at scale |
| **Weaviate** | Open source; rich filtering; GraphQL API | Additional service to deploy and manage |
| **Qdrant** | Open source; Rust performance; good filtering | Additional service; smaller ecosystem |
| **ChromaDB** | Simple; good for prototyping | Not production-grade for our needs; no native Postgres integration |

### Chunking Strategy

| Strategy | Description | Fit |
|----------|-------------|-----|
| **Per-skill-level** | One chunk per (skill_code, level) combination | Best granularity for our use case |
| **Per-skill** | One chunk per skill (all levels together) | Too coarse; levels have distinct descriptors |
| **Per-paragraph** | Generic text splitting | Loses structural semantics of SFIA |
| **Hierarchical** | Category → Subcategory → Skill → Level | Over-engineered for initial scale |

## Decision

### Vector Store: pgvector

pgvector is selected because:
- **Single database**: We already use PostgreSQL for application data. Adding pgvector avoids a separate vector database service.
- **Metadata filtering in SQL**: We can filter by `framework_type`, `skill_code`, `level`, and other metadata using standard SQL `WHERE` clauses combined with vector similarity search.
- **Scale is manageable**: SFIA 9 has ~120 skills × 7 levels = ~840 chunks. Even with multiple frameworks, we're unlikely to exceed 10,000 chunks. pgvector handles this trivially.
- **Operational simplicity**: One database to back up, monitor, and manage.
- **Hexagonal compliance**: The `KnowledgeBase` port abstracts the implementation. If we outgrow pgvector, we swap the adapter without touching domain logic.

### Chunking: Per-Skill-Level with Framework-Type Metadata

Each vector entry represents one (framework, skill, level) tuple:

```sql
CREATE TABLE skill_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_type  TEXT NOT NULL,        -- e.g., 'sfia-9', 'togaf', 'itil'
    framework_ver   TEXT NOT NULL,        -- e.g., '9.0'
    skill_code      TEXT NOT NULL,        -- e.g., 'PROG', 'ITMG', 'TEST'
    skill_name      TEXT NOT NULL,        -- e.g., 'Programming/Software Development'
    category        TEXT NOT NULL,        -- e.g., 'Development and implementation'
    subcategory     TEXT,                 -- e.g., 'Software design'
    level           INTEGER,             -- 1-7 (NULL for skill-level summary)
    content         TEXT NOT NULL,        -- The full text chunk
    embedding       vector(1536) NOT NULL,-- OpenAI text-embedding-3-small dimension
    metadata        JSONB DEFAULT '{}',   -- Extensible metadata
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_framework_skill_level 
        UNIQUE (framework_type, framework_ver, skill_code, level)
);

CREATE INDEX idx_skill_embeddings_embedding 
    ON skill_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX idx_skill_embeddings_framework 
    ON skill_embeddings (framework_type, framework_ver);

CREATE INDEX idx_skill_embeddings_skill 
    ON skill_embeddings (skill_code);
```

### Content Composition per Chunk

Each chunk's `content` field is composed as:

```
Framework: SFIA 9
Skill: {skill_name} ({skill_code})
Category: {category} > {subcategory}
Level: {level}

Description:
{level_description}

Autonomy: {autonomy_descriptor}
Influence: {influence_descriptor}
Complexity: {complexity_descriptor}
Knowledge: {knowledge_descriptor}
```

This gives the embedding model rich semantic content while keeping each chunk focused on a single skill-level combination.

### Query Strategy

The `SkillRetriever` class implements the `KnowledgeBase` port:

```python
class SkillRetriever:
    async def query(
        self,
        text: str,
        framework_type: str = "sfia-9",
        top_k: int = 5,
        level_filter: Optional[int] = None,
    ) -> list[SkillDefinition]:
        embedding = await self.embedder.embed(text)
        
        query = """
            SELECT skill_code, skill_name, level, content,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM skill_embeddings
            WHERE framework_type = $2
              AND ($3::int IS NULL OR level = $3)
            ORDER BY embedding <=> $1::vector
            LIMIT $4
        """
        
        results = await self.db.fetch(query, embedding, framework_type, level_filter, top_k)
        return [SkillDefinition.from_row(r) for r in results]
```

### Dynamic System Prompt Injection

During the call, retrieved skill definitions are injected into the LLM's system prompt:

```
You are an AI skills assessor. The candidate appears to be discussing skills 
related to the following SFIA definitions:

---
{retrieved_skill_definitions}
---

Based on these definitions, ask probing questions to determine the candidate's 
responsibility level (1-7) for each skill. Focus on evidence of:
- Autonomy: How independently do they work?
- Influence: What is their sphere of influence?
- Complexity: What complexity of work do they handle?
- Knowledge: What depth of knowledge do they demonstrate?
```

### Pluggability via `framework_type`

The `framework_type` metadata tag is the key extensibility mechanism:

1. **Adding a new framework**: Ingest chunks with a new `framework_type` value (e.g., `"togaf"`).
2. **Querying**: Pass the desired `framework_type` to `SkillRetriever.query()`.
3. **Mixed assessments**: Future versions could query multiple framework types in a single call.
4. **No schema changes**: The same table, same indexes, same query patterns apply.

## Embedding Model

**Selected**: OpenAI `text-embedding-3-small` (1536 dimensions)
- Good balance of quality and cost for our domain.
- Can be swapped via the embedding adapter without changing the retrieval logic.
- Alternative: `text-embedding-3-large` (3072 dimensions) if quality needs improvement.

## Consequences

**Positive:**
- Single PostgreSQL instance for both application data and vector search — minimal ops overhead.
- `framework_type` metadata makes the system future-proof for multi-framework support.
- Per-skill-level chunking gives optimal granularity for probing questions.
- SQL-based filtering is powerful and familiar to the team.
- Hexagonal architecture means pgvector can be swapped for Pinecone/Weaviate later if scale demands it.

**Negative:**
- pgvector's approximate nearest neighbour (IVFFlat) requires periodic re-indexing as data grows.
- Embedding model choice (OpenAI) introduces a dependency on an external API for ingestion.
- The embedding dimension (1536) is fixed per model — switching embedding models requires re-embedding all data.

## Migration Path

If pgvector becomes a bottleneck:
1. Implement a `PineconeKnowledgeBase` adapter (implements same `KnowledgeBase` port).
2. Run a migration script to upsert all chunks to Pinecone with identical metadata.
3. Swap the adapter in the composition root.
4. Domain logic and query interface remain unchanged.
