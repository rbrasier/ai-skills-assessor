/**
 * @ai-skills-assessor/shared-types
 *
 * Cross-service contracts used by the Next.js frontend (`apps/web`) and
 * the Python voice engine (`apps/voice-engine`).
 *
 * Phase 1 shipped only the trigger round-trip; Phase 2 extends this to
 * cover the full candidate intake flow (candidate + trigger + status +
 * cancel) and the admin session listing.
 */

// ─── Core status ─────────────────────────────────────────────────────

export type AssessmentStatus =
  | "pending"
  | "dialling"
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled";

// ─── Candidate intake (Step 01) ──────────────────────────────────────

export interface CandidateRequest {
  workEmail: string;
  firstName: string;
  lastName: string;
  employeeId: string;
}

export interface CandidateResponse {
  candidateId: string;
  workEmail: string;
  firstName: string;
  lastName: string;
}

// ─── Trigger a call (Step 02 start) ──────────────────────────────────

export interface TriggerCallRequest {
  candidateId: string;
  phoneNumber: string;
  dialingMethod?: string;
}

export interface TriggerCallResponse {
  sessionId: string;
  status: AssessmentStatus;
}

/**
 * Phase 1 alias — kept so existing importers continue to compile.
 * New code should prefer `TriggerCallRequest` / `TriggerCallResponse`.
 */
export interface AssessmentTriggerRequest {
  phoneNumber: string;
  candidateId: string;
}

export interface AssessmentTriggerResponse {
  sessionId: string;
  status: AssessmentStatus;
  createdAt: string;
}

// ─── Status polling (Step 02) ────────────────────────────────────────

export interface CallStatusResponse {
  sessionId: string;
  status: AssessmentStatus;
  durationSeconds: number;
  startedAt: string | null;
  endedAt: string | null;
  failureReason?: string | null;
  /** "daily" (PSTN) or "browser" (LiveKit). */
  dialingMethod?: string | null;
  /** When dialingMethod is "browser", URL for the candidate to open in the browser. */
  browserJoinUrl?: string | null;
  /** LiveKit room name (when dialingMethod is "browser"). */
  livekitRoomName?: string | null;
  /** LiveKit participant token (when dialingMethod is "browser"). */
  livekitParticipantToken?: string | null;
  /** LiveKit server URL. */
  livekitUrl?: string | null;
}

// ─── Admin dashboard ─────────────────────────────────────────────────

export interface SessionSummary {
  sessionId: string;
  candidateEmail: string;
  phoneNumber: string;
  status: AssessmentStatus;
  durationSeconds: number;
  createdAt: string;
  startedAt: string | null;
  endedAt: string | null;
}

export interface SessionListQuery {
  status?: AssessmentStatus;
  email?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

// ─── Phase 7: Review portal types ────────────────────────────────────

export type SupervisorDecision = "pending" | "verified" | "rejected";

export interface Claim {
  id: string;
  sessionId?: string;
  verbatimQuote: string;
  interpretedClaim: string;
  skillCode: string;
  skillName: string;
  level: number;
  confidence: number;
  reasoning?: string;
  expertLevel?: number | null;
  supervisorDecision?: SupervisorDecision | null;
  supervisorComment?: string | null;
}

export type ReportStatus =
  | "generated"
  | "sent"
  | "awaiting_expert"
  | "awaiting_supervisor"
  | "reviews_complete"
  | "in_review"
  | "completed";

export interface AssessmentReport {
  sessionId: string;
  candidateName: string | null;
  expertReviewToken: string | null;
  supervisorReviewToken: string | null;
  overallConfidence: number | null;
  reportStatus: ReportStatus | null;
  claimsJson: Claim[];
  reportGeneratedAt: string | null;
  expiresAt: string | null;
  expertSubmittedAt: string | null;
  expertReviewerName: string | null;
  expertReviewerEmail: string | null;
  supervisorSubmittedAt: string | null;
  supervisorReviewerName: string | null;
  supervisorReviewerEmail: string | null;
  reviewsCompletedAt: string | null;
}

export interface ExpertReviewClaimItem {
  id: string;
  expertLevel: number;
}

export interface ExpertReviewPayload {
  reviewerFullName: string;
  reviewerEmail: string;
  claims: ExpertReviewClaimItem[];
}

export interface SupervisorReviewClaimItem {
  id: string;
  supervisorDecision: "verified" | "rejected";
  supervisorComment?: string;
}

export interface SupervisorReviewPayload {
  reviewerFullName: string;
  reviewerEmail: string;
  claims: SupervisorReviewClaimItem[];
}

export interface ReviewSaveResponse {
  sessionId: string;
  reportStatus: ReportStatus;
  reviewsCompletedAt: string | null;
  claims: Claim[];
}

// ─── Phase 7: Enriched admin session summary ─────────────────────────

export interface AdminSessionSummary extends SessionSummary {
  candidateName: string | null;
  reportStatus: ReportStatus | null;
  expertReviewToken: string | null;
  supervisorReviewToken: string | null;
  maxSfiaLevel: number | null;
  overallConfidence: number | null;
  topSkillCodes: string[];
}

// ─── Phase 7: Stats / chart aggregates ──────────────────────────────

export interface DailyCallCount {
  date: string;
  count: number;
}

export interface OutcomeBucket {
  label: string;
  count: number;
  color: string;
}

export interface AdminStats {
  totalCalls: number;
  avgDurationMinutes: number;
  completionRatePct: number;
  awaitingReviewCount: number;
  avgSfiaLevel: number;
  callsPerDay: DailyCallCount[];
  outcomeBuckets: OutcomeBucket[];
}
