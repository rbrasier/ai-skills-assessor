-- AI Skills Assessor — v0.6.2
--
-- Additive migration: add holistic_assessment_json column to assessment_sessions.
-- The holistic assessment is a full-transcript skill profile produced by
-- analyse_transcript_holistically() and stored alongside claims_json.

ALTER TABLE "assessment_sessions"
    ADD COLUMN IF NOT EXISTS "holistic_assessment_json" JSONB;
