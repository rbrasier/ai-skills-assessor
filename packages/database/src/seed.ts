/**
 * Database seed script — demo data for local development and admin dashboard testing.
 *
 * Creates:
 *   - 6 demo candidates
 *   - 8 assessment sessions covering all meaningful states:
 *       completed + reviews_complete, completed + awaiting_expert,
 *       completed + awaiting_supervisor, in_progress, failed,
 *       cancelled, user_ended, pending
 *   - Realistic claims_json and holistic_assessment_json for completed sessions
 *   - Monitoring fields (termination_reason, focus_suspicious, total_focus_away_ms)
 *
 * Safe to re-run: uses upsert for candidates and deleteMany + create for sessions.
 */

import { PrismaClient } from "./generated/client/index.js";
import { randomUUID } from "crypto";

const prisma = new PrismaClient();

// ─── Helpers ─────────────────────────────────────────────────────────────────

function nanoid(len = 21): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  return Array.from({ length: len }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
}

function daysAgo(n: number): Date {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d;
}

function addMinutes(base: Date, m: number): Date {
  return new Date(base.getTime() + m * 60_000);
}

// ─── Claim factory ───────────────────────────────────────────────────────────

interface ClaimInput {
  verbatim: string;
  interpreted: string;
  summary: string;
  claim_type: "sme" | "supervisor";
  skill_code: string;
  skill_name: string;
  level: number;
  confidence: number;
  reasoning: string;
  supervisor_decision?: "pending" | "verified" | "rejected";
  expert_level?: number;
}

function makeClaim(c: ClaimInput) {
  return {
    id: randomUUID(),
    verbatim_quote: c.verbatim,
    interpreted_claim: c.interpreted,
    summary: c.summary,
    claim_type: c.claim_type,
    sfia_skill_code: c.skill_code,
    sfia_skill_name: c.skill_name,
    sfia_level: c.level,
    confidence: c.confidence,
    reasoning: c.reasoning,
    framework_type: "sfia-9",
    evidence_segments: [],
    expert_level: c.expert_level ?? null,
    supervisor_decision: c.supervisor_decision ?? "pending",
    supervisor_comment: null,
    sme_status: "pending",
    sme_adjusted_level: null,
    sme_notes: null,
  };
}

// ─── Demo candidates ─────────────────────────────────────────────────────────

const CANDIDATES = [
  { email: "alice.chen@helixcorp.com.au",   firstName: "Alice",   lastName: "Chen" },
  { email: "ben.murphy@helixcorp.com.au",    firstName: "Ben",     lastName: "Murphy" },
  { email: "chloe.evans@helixcorp.com.au",  firstName: "Chloe",   lastName: "Evans" },
  { email: "david.kim@helixcorp.com.au",    firstName: "David",   lastName: "Kim" },
  { email: "emma.wilson@helixcorp.com.au",  firstName: "Emma",    lastName: "Wilson" },
  { email: "frank.osei@helixcorp.com.au",   firstName: "Frank",   lastName: "Osei" },
];

// ─── Demo sessions ────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log("[seed] Upserting demo candidates…");

  for (const c of CANDIDATES) {
    await prisma.candidate.upsert({
      where: { email: c.email },
      update: { firstName: c.firstName, lastName: c.lastName },
      create: { email: c.email, firstName: c.firstName, lastName: c.lastName },
    });
  }

  console.log("[seed] Clearing existing demo sessions…");
  await prisma.assessmentSession.deleteMany({
    where: { candidateId: { in: CANDIDATES.map((c) => c.email) } },
  });

  // ── Session 1: Completed, reviews complete ────────────────────────────────
  const s1Start = daysAgo(14);
  await prisma.assessmentSession.create({
    data: {
      id: randomUUID(),
      candidateId: "alice.chen@helixcorp.com.au",
      candidateName: "Alice Chen",
      phoneNumber: "+61 412 345 678",
      status: "completed",
      startedAt: s1Start,
      endedAt: addMinutes(s1Start, 38),
      createdAt: daysAgo(14),
      expertReviewToken: nanoid(),
      supervisorReviewToken: nanoid(),
      reportStatus: "reviews_complete",
      overallConfidence: 0.82,
      reportGeneratedAt: addMinutes(s1Start, 45),
      expiresAt: addMinutes(s1Start, 60 * 24 * 30),
      expertSubmittedAt: daysAgo(12),
      expertReviewerName: "Dr. Sarah Lim",
      expertReviewerEmail: "s.lim@reviewer.com.au",
      supervisorSubmittedAt: daysAgo(10),
      supervisorReviewerName: "James Park",
      supervisorReviewerEmail: "j.park@helixcorp.com.au",
      reviewsCompletedAt: daysAgo(10),
      terminationReason: "user_ended",
      focusSuspicious: false,
      totalFocusAwayMs: 0,
      claimsJson: [
        makeClaim({
          verbatim: "I led the migration of our monolithic Rails app to a microservices architecture using Kubernetes and Docker, coordinating four backend engineers over six months.",
          interpreted: "Candidate architected and led a microservices migration using Kubernetes.",
          summary: "Led microservices migration on Kubernetes",
          claim_type: "sme",
          skill_code: "ARCH",
          skill_name: "Solution Architecture",
          level: 5,
          confidence: 0.88,
          reasoning: "Describes architectural decision-making and technical leadership consistent with SFIA level 5.",
          expert_level: 5,
          supervisor_decision: "verified",
        }),
        makeClaim({
          verbatim: "We reduced P95 latency from 800ms to 120ms by implementing a Redis caching layer and optimising our PostgreSQL queries with EXPLAIN ANALYSE.",
          interpreted: "Candidate optimised system performance through caching and query tuning.",
          summary: "Reduced latency with Redis cache and query optimisation",
          claim_type: "sme",
          skill_code: "DESN",
          skill_name: "Systems Design",
          level: 4,
          confidence: 0.85,
          reasoning: "Performance optimisation with measurable outcomes indicates strong technical depth at level 4.",
          expert_level: 4,
          supervisor_decision: "verified",
        }),
        makeClaim({
          verbatim: "That project ran for about nine months, not six — we started in January and went live in October.",
          interpreted: "Project duration was nine months (January to October).",
          summary: "Microservices project ran January to October (9 months)",
          claim_type: "supervisor",
          skill_code: "ARCH",
          skill_name: "Solution Architecture",
          level: 0,
          confidence: 0.95,
          reasoning: "Factual project timeline claim suitable for supervisor verification.",
          supervisor_decision: "verified",
        }),
      ],
      holisticAssessmentJson: [
        { skill_code: "ARCH", skill_name: "Solution Architecture", estimated_level: 5, prominence: 0.65, evidence_summary: "Strong architectural decision-making and microservices leadership." },
        { skill_code: "DESN", skill_name: "Systems Design", estimated_level: 4, prominence: 0.35, evidence_summary: "Solid evidence of performance design and optimisation." },
      ],
    },
  });

  // ── Session 2: Completed, awaiting expert review ──────────────────────────
  const s2Start = daysAgo(3);
  await prisma.assessmentSession.create({
    data: {
      id: randomUUID(),
      candidateId: "ben.murphy@helixcorp.com.au",
      candidateName: "Ben Murphy",
      phoneNumber: "+61 423 456 789",
      status: "completed",
      startedAt: s2Start,
      endedAt: addMinutes(s2Start, 42),
      createdAt: daysAgo(3),
      expertReviewToken: nanoid(),
      supervisorReviewToken: nanoid(),
      reportStatus: "awaiting_expert",
      overallConfidence: 0.74,
      reportGeneratedAt: addMinutes(s2Start, 50),
      expiresAt: addMinutes(s2Start, 60 * 24 * 30),
      terminationReason: "user_ended",
      focusSuspicious: false,
      totalFocusAwayMs: 4200,
      claimsJson: [
        makeClaim({
          verbatim: "I built a CI/CD pipeline using GitHub Actions and Terraform that provisions infrastructure on AWS and deploys our Node.js services automatically on every merge to main.",
          interpreted: "Candidate implemented automated CI/CD with infrastructure as code on AWS.",
          summary: "Built GitHub Actions + Terraform CI/CD pipeline on AWS",
          claim_type: "sme",
          skill_code: "SYSP",
          skill_name: "Systems and Software Lifecycle Management",
          level: 4,
          confidence: 0.79,
          reasoning: "Demonstrates ownership of the delivery pipeline including IaC, consistent with level 4.",
        }),
        makeClaim({
          verbatim: "I've been at Helix for two years and three months working in the platform team.",
          interpreted: "Candidate has been employed at Helix for approximately 27 months in the platform team.",
          summary: "27 months at Helix in platform team",
          claim_type: "supervisor",
          skill_code: "SYSP",
          skill_name: "Systems and Software Lifecycle Management",
          level: 0,
          confidence: 0.92,
          reasoning: "Employment duration and team placement — factual claim for supervisor.",
        }),
      ],
      holisticAssessmentJson: [
        { skill_code: "SYSP", skill_name: "Systems and Software Lifecycle Management", estimated_level: 4, prominence: 0.8, evidence_summary: "Strong CI/CD and infrastructure automation skills." },
        { skill_code: "DESN", skill_name: "Systems Design", estimated_level: 3, prominence: 0.2, evidence_summary: "Some evidence of design work; insufficient for higher level." },
      ],
    },
  });

  // ── Session 3: Completed, awaiting supervisor review ─────────────────────
  const s3Start = daysAgo(5);
  await prisma.assessmentSession.create({
    data: {
      id: randomUUID(),
      candidateId: "chloe.evans@helixcorp.com.au",
      candidateName: "Chloe Evans",
      phoneNumber: "+61 434 567 890",
      status: "completed",
      startedAt: s3Start,
      endedAt: addMinutes(s3Start, 29),
      createdAt: daysAgo(5),
      expertReviewToken: nanoid(),
      supervisorReviewToken: nanoid(),
      reportStatus: "awaiting_supervisor",
      overallConfidence: 0.68,
      reportGeneratedAt: addMinutes(s3Start, 35),
      expiresAt: addMinutes(s3Start, 60 * 24 * 30),
      expertSubmittedAt: daysAgo(4),
      expertReviewerName: "Dr. Sarah Lim",
      expertReviewerEmail: "s.lim@reviewer.com.au",
      terminationReason: "user_ended",
      focusSuspicious: true,
      totalFocusAwayMs: 95_000,
      focusEventsJson: [
        { at: addMinutes(s3Start, 12).toISOString(), phase: "evidence_gathering", durationMs: 62_000 },
        { at: addMinutes(s3Start, 21).toISOString(), phase: "evidence_gathering", durationMs: 33_000 },
      ],
      claimsJson: [
        makeClaim({
          verbatim: "I designed and ran a user research programme interviewing 20 stakeholders to define acceptance criteria for our new data platform.",
          interpreted: "Candidate ran stakeholder research to define requirements for a data platform.",
          summary: "Led 20-person stakeholder interviews for data platform requirements",
          claim_type: "sme",
          skill_code: "BUAN",
          skill_name: "Business Analysis",
          level: 4,
          confidence: 0.71,
          reasoning: "Structured requirements gathering with stakeholders consistent with level 4 business analysis.",
          expert_level: 4,
          supervisor_decision: "pending",
        }),
      ],
      holisticAssessmentJson: [
        { skill_code: "BUAN", skill_name: "Business Analysis", estimated_level: 4, prominence: 0.9, evidence_summary: "Clear evidence of requirements gathering and stakeholder management." },
      ],
    },
  });

  // ── Session 4: In progress ────────────────────────────────────────────────
  const s4Start = new Date(Date.now() - 18 * 60_000); // started 18 min ago
  await prisma.assessmentSession.create({
    data: {
      id: randomUUID(),
      candidateId: "david.kim@helixcorp.com.au",
      candidateName: "David Kim",
      phoneNumber: "+61 445 678 901",
      status: "in_progress",
      startedAt: s4Start,
      createdAt: new Date(Date.now() - 20 * 60_000),
      focusSuspicious: false,
      totalFocusAwayMs: 0,
    },
  });

  // ── Session 5: Failed (WebSocket error) ──────────────────────────────────
  const s5Start = daysAgo(7);
  await prisma.assessmentSession.create({
    data: {
      id: randomUUID(),
      candidateId: "emma.wilson@helixcorp.com.au",
      candidateName: "Emma Wilson",
      phoneNumber: "+61 456 789 012",
      status: "failed",
      startedAt: s5Start,
      endedAt: addMinutes(s5Start, 3),
      createdAt: daysAgo(7),
      terminationReason: "websocket_error",
      errorDetails: { message: "WebSocket closed unexpectedly", code: 1006 },
      focusSuspicious: false,
      totalFocusAwayMs: 0,
    },
  });

  // ── Session 6: Cancelled ──────────────────────────────────────────────────
  await prisma.assessmentSession.create({
    data: {
      id: randomUUID(),
      candidateId: "emma.wilson@helixcorp.com.au",
      candidateName: "Emma Wilson",
      phoneNumber: "+61 456 789 012",
      status: "cancelled",
      createdAt: daysAgo(2),
      terminationReason: "admin_cancelled",
      focusSuspicious: false,
      totalFocusAwayMs: 0,
    },
  });

  // ── Session 7: User ended early (completed with short duration) ───────────
  const s7Start = daysAgo(1);
  await prisma.assessmentSession.create({
    data: {
      id: randomUUID(),
      candidateId: "frank.osei@helixcorp.com.au",
      candidateName: "Frank Osei",
      phoneNumber: "+61 467 890 123",
      status: "user_ended",
      startedAt: s7Start,
      endedAt: addMinutes(s7Start, 6),
      createdAt: daysAgo(1),
      terminationReason: "user_ended",
      focusSuspicious: false,
      totalFocusAwayMs: 0,
    },
  });

  // ── Session 8: Pending (just scheduled) ──────────────────────────────────
  await prisma.assessmentSession.create({
    data: {
      id: randomUUID(),
      candidateId: "frank.osei@helixcorp.com.au",
      candidateName: "Frank Osei",
      phoneNumber: "+61 467 890 123",
      status: "pending",
      createdAt: new Date(),
    },
  });

  console.log("[seed] Done — 6 candidates, 8 sessions created.");
  await prisma.$disconnect();
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error("[seed] failed:", err);
  void prisma.$disconnect();
  process.exit(1);
});
