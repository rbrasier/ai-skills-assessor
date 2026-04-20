import type {
  AssessmentTriggerRequest,
  AssessmentTriggerResponse,
  CallStatusResponse,
  CandidateResponse,
  SessionSummary,
  TriggerCallResponse,
} from "@ai-skills-assessor/shared-types";

/**
 * Thin browser-side client for the Phase 2 assessment endpoints. All
 * calls go through the Next.js API routes, which in turn proxy to the
 * Python voice engine so we have a single place to add auth headers,
 * retries, and telemetry later.
 */

export interface CreateCandidatePayload {
  workEmail: string;
  firstName: string;
  lastName: string;
  employeeId: string;
}

export async function createCandidate(
  payload: CreateCandidatePayload,
): Promise<CandidateResponse> {
  const response = await fetch("/api/assessment/candidate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Invalid form data. Please update and try again.");
  }
  return (await response.json()) as CandidateResponse;
}

export interface TriggerCallPayload {
  candidateId: string;
  phoneNumber: string;
}

export async function triggerCall(payload: TriggerCallPayload): Promise<TriggerCallResponse> {
  const response = await fetch("/api/assessment/trigger", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Invalid form data. Please update and try again.");
  }
  return (await response.json()) as TriggerCallResponse;
}

export async function fetchCallStatus(sessionId: string): Promise<CallStatusResponse> {
  const response = await fetch(`/api/assessment/${sessionId}/status`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Status request failed (${response.status})`);
  return (await response.json()) as CallStatusResponse;
}

export async function cancelCall(sessionId: string): Promise<CallStatusResponse> {
  const response = await fetch(`/api/assessment/${sessionId}/cancel`, { method: "POST" });
  if (!response.ok) throw new Error(`Cancel failed (${response.status})`);
  return (await response.json()) as CallStatusResponse;
}

export interface ListSessionsQuery {
  status?: string;
  email?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

export async function listSessions(query: ListSessionsQuery = {}): Promise<SessionSummary[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const url = `/api/admin/sessions${params.size ? `?${params.toString()}` : ""}`;
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`Admin list failed (${response.status})`);
  return (await response.json()) as SessionSummary[];
}

/**
 * Phase 1 alias — kept so any earlier code that imported
 * ``triggerAssessment`` continues to compile.
 */
export async function triggerAssessment(
  payload: AssessmentTriggerRequest,
): Promise<AssessmentTriggerResponse> {
  const response = await fetch("/api/assessment/trigger", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      candidateId: payload.candidateId,
      phoneNumber: payload.phoneNumber,
    }),
  });
  if (!response.ok) {
    throw new Error(`Failed to trigger assessment (${response.status})`);
  }
  const body = (await response.json()) as TriggerCallResponse;
  return {
    sessionId: body.sessionId,
    status: body.status,
    createdAt: new Date().toISOString(),
  };
}
