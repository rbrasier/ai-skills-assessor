-- AI Skills Assessor — Phase 6 Revision: Dual Review Tokens
--
-- Replaces the single review_token with separate expert and supervisor tokens.
-- Adds reviewer audit columns for both roles.
-- report_status VARCHAR widened to 30 to accommodate new enum values.
--
-- The original review_token column is retained as deprecated during transition;
-- drop it in a future migration once all rows are migrated.

-- ──────────────────────────────────────────────────────────────
-- 1. Dual review token columns
-- ──────────────────────────────────────────────────────────────

ALTER TABLE "assessment_sessions"
    ADD COLUMN IF NOT EXISTS "expert_review_token"      VARCHAR(21),
    ADD COLUMN IF NOT EXISTS "supervisor_review_token"  VARCHAR(21);

-- ──────────────────────────────────────────────────────────────
-- 2. Expert reviewer audit columns
-- ──────────────────────────────────────────────────────────────

ALTER TABLE "assessment_sessions"
    ADD COLUMN IF NOT EXISTS "expert_submitted_at"      TIMESTAMP(3),
    ADD COLUMN IF NOT EXISTS "expert_reviewer_name"     VARCHAR(255),
    ADD COLUMN IF NOT EXISTS "expert_reviewer_email"    VARCHAR(255);

-- ──────────────────────────────────────────────────────────────
-- 3. Supervisor reviewer audit columns
-- ──────────────────────────────────────────────────────────────

ALTER TABLE "assessment_sessions"
    ADD COLUMN IF NOT EXISTS "supervisor_submitted_at"      TIMESTAMP(3),
    ADD COLUMN IF NOT EXISTS "supervisor_reviewer_name"     VARCHAR(255),
    ADD COLUMN IF NOT EXISTS "supervisor_reviewer_email"    VARCHAR(255),
    ADD COLUMN IF NOT EXISTS "reviews_completed_at"         TIMESTAMP(3);

-- ──────────────────────────────────────────────────────────────
-- 4. Widen report_status to hold new workflow enum values
-- ──────────────────────────────────────────────────────────────

ALTER TABLE "assessment_sessions"
    ALTER COLUMN "report_status" TYPE VARCHAR(30);

-- ──────────────────────────────────────────────────────────────
-- 5. Indexes for efficient token lookups
-- ──────────────────────────────────────────────────────────────

CREATE UNIQUE INDEX IF NOT EXISTS "assessment_sessions_expert_token_key"
    ON "assessment_sessions" ("expert_review_token")
    WHERE "expert_review_token" IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS "assessment_sessions_supervisor_token_key"
    ON "assessment_sessions" ("supervisor_review_token")
    WHERE "supervisor_review_token" IS NOT NULL;
