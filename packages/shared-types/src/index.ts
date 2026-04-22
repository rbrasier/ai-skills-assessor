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
