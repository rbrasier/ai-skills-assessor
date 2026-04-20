-- AI Skills Assessor — Phase 2 schema (v0.3.0).
--
-- Rebuilds `candidates` with `email` as the primary key (plus a JSONB
-- `metadata` column for `employee_id` and other extensible fields), and
-- extends `assessment_sessions` with a `metadata` JSONB column, a
-- `createdAt` index, and the re-keyed candidate FK.
--
-- Phase 1 shipped no production data; this migration is authored as a
-- fresh drop-and-replace of the two tables. If any data existed, it
-- would need to be migrated manually before running this file.

-- DropForeignKey
ALTER TABLE IF EXISTS "assessment_sessions"
    DROP CONSTRAINT IF EXISTS "assessment_sessions_candidateId_fkey";

-- DropTable
DROP TABLE IF EXISTS "assessment_sessions";
DROP TABLE IF EXISTS "candidates";

-- CreateTable
CREATE TABLE "candidates" (
    "email" VARCHAR(255) NOT NULL,
    "firstName" VARCHAR(255) NOT NULL,
    "lastName" VARCHAR(255) NOT NULL,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "candidates_pkey" PRIMARY KEY ("email")
);

-- CreateTable
CREATE TABLE "assessment_sessions" (
    "id" TEXT NOT NULL,
    "candidateId" VARCHAR(255) NOT NULL,
    "phoneNumber" VARCHAR(32) NOT NULL,
    "status" VARCHAR(32) NOT NULL DEFAULT 'pending',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "dailyRoomUrl" TEXT,
    "recordingUrl" TEXT,
    "startedAt" TIMESTAMP(3),
    "endedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "assessment_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "candidates_createdAt_idx" ON "candidates"("createdAt");

-- CreateIndex
CREATE INDEX "assessment_sessions_candidateId_idx" ON "assessment_sessions"("candidateId");

-- CreateIndex
CREATE INDEX "assessment_sessions_candidateId_createdAt_idx" ON "assessment_sessions"("candidateId", "createdAt");

-- CreateIndex
CREATE INDEX "assessment_sessions_status_idx" ON "assessment_sessions"("status");

-- CreateIndex
CREATE INDEX "assessment_sessions_createdAt_idx" ON "assessment_sessions"("createdAt");

-- AddForeignKey
ALTER TABLE "assessment_sessions"
    ADD CONSTRAINT "assessment_sessions_candidateId_fkey"
    FOREIGN KEY ("candidateId") REFERENCES "candidates"("email")
    ON DELETE CASCADE ON UPDATE CASCADE;
