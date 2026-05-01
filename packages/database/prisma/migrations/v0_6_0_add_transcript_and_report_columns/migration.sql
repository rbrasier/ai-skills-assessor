-- AI Skills Assessor — Phase 6 schema (v0.6.0).
--
-- Additive migration:
--   1. Add 9 new columns to assessment_sessions for claim extraction pipeline.
--   2. Promote transcript_json from metadata JSONB to dedicated column.
--   3. Add indexes for efficient report lookups.
--
-- No existing tables are dropped or altered (other than additive columns).

-- ──────────────────────────────────────────────────────────────
-- 1. New columns on assessment_sessions
-- ──────────────────────────────────────────────────────────────

ALTER TABLE "assessment_sessions"
    ADD COLUMN IF NOT EXISTS "candidate_name"       VARCHAR(255),
    ADD COLUMN IF NOT EXISTS "transcript_json"      JSONB,
    ADD COLUMN IF NOT EXISTS "claims_json"          JSONB,
    ADD COLUMN IF NOT EXISTS "review_token"         VARCHAR(21),
    ADD COLUMN IF NOT EXISTS "report_status"        VARCHAR(20),
    ADD COLUMN IF NOT EXISTS "overall_confidence"   FLOAT,
    ADD COLUMN IF NOT EXISTS "report_generated_at"  TIMESTAMP(3),
    ADD COLUMN IF NOT EXISTS "sme_reviewed_at"      TIMESTAMP(3),
    ADD COLUMN IF NOT EXISTS "expires_at"           TIMESTAMP(3);

-- ──────────────────────────────────────────────────────────────
-- 2. Indexes for efficient lookups
-- ──────────────────────────────────────────────────────────────

CREATE UNIQUE INDEX IF NOT EXISTS "assessment_sessions_review_token_key"
    ON "assessment_sessions" ("review_token")
    WHERE "review_token" IS NOT NULL;

CREATE INDEX IF NOT EXISTS "assessment_sessions_report_status_idx"
    ON "assessment_sessions" ("report_status")
    WHERE "report_status" IS NOT NULL;

-- ──────────────────────────────────────────────────────────────
-- 3. Data migration: promote transcript_json from metadata JSONB
-- ──────────────────────────────────────────────────────────────

UPDATE "assessment_sessions"
SET "transcript_json" = ("metadata"->>'transcript_json')::jsonb
WHERE "metadata" ? 'transcript_json'
  AND "transcript_json" IS NULL;
