/**
 * @ai-skills-assessor/shared-types
 *
 * Minimal cross-service contracts used by the Next.js frontend (`apps/web`)
 * and the Python voice engine (`apps/voice-engine`). Phase 1 only covers the
 * "trigger an assessment call" round-trip; richer contracts (claims, reports,
 * SFIA mappings) are added in later phases.
 */

export type AssessmentStatus =
  | "pending"
  | "dialling"
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled";

export interface AssessmentTriggerRequest {
  /** E.164 phone number, e.g. `+61412345678`. */
  phoneNumber: string;
  /** Internal candidate identifier (UUID). */
  candidateId: string;
}

export interface AssessmentTriggerResponse {
  sessionId: string;
  status: AssessmentStatus;
  /** ISO-8601 timestamp. */
  createdAt: string;
}
