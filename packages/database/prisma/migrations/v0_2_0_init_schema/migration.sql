-- AI Skills Assessor — initial schema (v0.2.0)
-- Creates `candidates` and `assessment_sessions` tables.

-- CreateTable
CREATE TABLE "candidates" (
    "id" TEXT NOT NULL,
    "firstName" VARCHAR(255) NOT NULL,
    "lastName" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "phoneNumber" VARCHAR(20) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "candidates_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "assessment_sessions" (
    "id" TEXT NOT NULL,
    "candidateId" TEXT NOT NULL,
    "phoneNumber" VARCHAR(20) NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "dailyRoomUrl" TEXT,
    "recordingUrl" TEXT,
    "startedAt" TIMESTAMP(3),
    "endedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "assessment_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "candidates_email_key" ON "candidates"("email");

-- CreateIndex
CREATE INDEX "candidates_email_idx" ON "candidates"("email");

-- CreateIndex
CREATE INDEX "candidates_createdAt_idx" ON "candidates"("createdAt");

-- CreateIndex
CREATE INDEX "assessment_sessions_candidateId_idx" ON "assessment_sessions"("candidateId");

-- CreateIndex
CREATE INDEX "assessment_sessions_candidateId_createdAt_idx" ON "assessment_sessions"("candidateId", "createdAt");

-- CreateIndex
CREATE INDEX "assessment_sessions_status_idx" ON "assessment_sessions"("status");

-- AddForeignKey
ALTER TABLE "assessment_sessions"
    ADD CONSTRAINT "assessment_sessions_candidateId_fkey"
    FOREIGN KEY ("candidateId") REFERENCES "candidates"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
