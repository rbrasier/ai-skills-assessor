-- AI Skills Assessor — v0.8.0
--
-- Monitoring & assessment integrity features.
-- Purely additive — all new columns use ADD COLUMN IF NOT EXISTS and
-- CREATE TABLE IF NOT EXISTS so re-running is safe.
--
-- Changes:
--   1. assessment_sessions — add structured termination + focus integrity columns
--   2. candidates          — add cooldown override + restriction control columns
--   3. admin_settings      — singleton platform-wide configuration table
--   4. candidate_restriction_audit — immutable log of restriction actions

-- ──────────────────────────────────────────────────────────────────────────────
-- 1. assessment_sessions: monitoring columns
-- ──────────────────────────────────────────────────────────────────────────────

ALTER TABLE "assessment_sessions"
    ADD COLUMN IF NOT EXISTS "termination_reason"  VARCHAR(50),
    ADD COLUMN IF NOT EXISTS "error_details"        JSONB,
    ADD COLUMN IF NOT EXISTS "last_turn_saved_at"   TIMESTAMP(3),
    ADD COLUMN IF NOT EXISTS "focus_suspicious"     BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS "total_focus_away_ms"  INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS "focus_events_json"    JSONB;

-- ──────────────────────────────────────────────────────────────────────────────
-- 2. candidates: cooldown override + no-restriction flag
-- ──────────────────────────────────────────────────────────────────────────────

ALTER TABLE "candidates"
    ADD COLUMN IF NOT EXISTS "cooldown_override_granted_at" TIMESTAMP(3),
    ADD COLUMN IF NOT EXISTS "cooldown_override_expires_at" TIMESTAMP(3),
    ADD COLUMN IF NOT EXISTS "no_restrictions"              BOOLEAN NOT NULL DEFAULT FALSE;

-- ──────────────────────────────────────────────────────────────────────────────
-- 3. admin_settings: singleton configuration row
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS "admin_settings" (
    "id"           TEXT         NOT NULL DEFAULT 'default',
    "cooldownDays" INTEGER      NOT NULL DEFAULT 90,
    "updatedAt"    TIMESTAMP(3) NOT NULL,
    "updatedBy"    VARCHAR(255),

    CONSTRAINT "admin_settings_pkey" PRIMARY KEY ("id")
);

-- ──────────────────────────────────────────────────────────────────────────────
-- 4. candidate_restriction_audit: immutable action log
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS "candidate_restriction_audit" (
    "id"          TEXT         NOT NULL DEFAULT gen_random_uuid()::text,
    "candidateId" VARCHAR(255) NOT NULL,
    "action"      VARCHAR(50)  NOT NULL,
    "grantedBy"   VARCHAR(255) NOT NULL,
    "expiresAt"   TIMESTAMP(3),
    "reason"      TEXT,
    "createdAt"   TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "candidate_restriction_audit_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "candidate_restriction_audit_candidateId_idx"
    ON "candidate_restriction_audit"("candidateId");

CREATE INDEX IF NOT EXISTS "candidate_restriction_audit_createdAt_idx"
    ON "candidate_restriction_audit"("createdAt");

ALTER TABLE "candidate_restriction_audit"
    DROP CONSTRAINT IF EXISTS "candidate_restriction_audit_candidateId_fkey";

ALTER TABLE "candidate_restriction_audit"
    ADD CONSTRAINT "candidate_restriction_audit_candidateId_fkey"
    FOREIGN KEY ("candidateId") REFERENCES "candidates"("email")
    ON DELETE CASCADE ON UPDATE CASCADE;
