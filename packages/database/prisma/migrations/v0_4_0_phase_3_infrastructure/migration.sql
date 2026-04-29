-- AI Skills Assessor — Phase 3 schema (v0.4.0).
--
-- Purely additive migration:
--   1. Enable pgvector extension (required by ADR-005 for RAG).
--   2. Create `skill_embeddings` (filled by Phase 5 ingestion).
--   3. Create `assessment_reports` scaffold (fleshed out in Phase 6).
--
-- No existing tables are dropped or altered — safe on a populated
-- database.

-- ──────────────────────────────────────────────────────────────
-- 1. pgvector extension
-- ──────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS vector;

-- ──────────────────────────────────────────────────────────────
-- 2. skill_embeddings table
-- ──────────────────────────────────────────────────────────────

CREATE TABLE "skill_embeddings" (
    "id" TEXT NOT NULL,
    "frameworkType" VARCHAR(50) NOT NULL,
    "frameworkVersion" VARCHAR(20) NOT NULL,
    "skillCode" VARCHAR(50) NOT NULL,
    "skillName" VARCHAR(255) NOT NULL,
    "category" VARCHAR(100) NOT NULL,
    "subcategory" VARCHAR(100),
    "level" INTEGER,
    "content" TEXT NOT NULL,
    "embedding" vector(1536),
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "skill_embeddings_pkey" PRIMARY KEY ("id")
);

-- Uniqueness: one row per (framework, version, skill, level) tuple.
CREATE UNIQUE INDEX "skill_embeddings_frameworkType_frameworkVersion_skillCode_level_key"
    ON "skill_embeddings"("frameworkType", "frameworkVersion", "skillCode", "level");

CREATE INDEX "skill_embeddings_frameworkType_idx"
    ON "skill_embeddings"("frameworkType");

CREATE INDEX "skill_embeddings_frameworkType_level_idx"
    ON "skill_embeddings"("frameworkType", "level");

CREATE INDEX "skill_embeddings_skillCode_idx"
    ON "skill_embeddings"("skillCode");

-- Approximate-nearest-neighbour index on the embedding column
-- (ADR-005). Uses ivfflat with cosine distance — adequate for the
-- ~10k-row SFIA corpus. `lists` can be retuned later.
CREATE INDEX "skill_embeddings_embedding_idx"
    ON "skill_embeddings" USING ivfflat ("embedding" vector_cosine_ops)
    WITH (lists = 100);

-- ──────────────────────────────────────────────────────────────
-- 3. assessment_reports scaffold
-- ──────────────────────────────────────────────────────────────

CREATE TABLE "assessment_reports" (
    "id" TEXT NOT NULL,
    "sessionId" TEXT NOT NULL,
    "reviewToken" VARCHAR(50) NOT NULL,
    "status" VARCHAR(32) NOT NULL DEFAULT 'generated',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "generatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "smeReviewedAt" TIMESTAMP(3),
    "expiresAt" TIMESTAMP(3),

    CONSTRAINT "assessment_reports_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "assessment_reports_sessionId_key"
    ON "assessment_reports"("sessionId");

CREATE UNIQUE INDEX "assessment_reports_reviewToken_key"
    ON "assessment_reports"("reviewToken");

CREATE INDEX "assessment_reports_reviewToken_idx"
    ON "assessment_reports"("reviewToken");

CREATE INDEX "assessment_reports_status_idx"
    ON "assessment_reports"("status");

CREATE INDEX "assessment_reports_generatedAt_idx"
    ON "assessment_reports"("generatedAt");

ALTER TABLE "assessment_reports"
    ADD CONSTRAINT "assessment_reports_sessionId_fkey"
    FOREIGN KEY ("sessionId") REFERENCES "assessment_sessions"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
