import type {
  AdminSessionSummary,
  AdminStats,
  AssessmentReport,
  AssessmentTriggerRequest,
  AssessmentTriggerResponse,
  CallStatusResponse,
  CandidateResponse,
  ExpertReviewPayload,
  ReviewSaveResponse,
  SessionSummary,
  SupervisorReviewPayload,
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
  phoneNumber?: string;
  dialingMethod?: string;
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

// ─── Phase 7: Review portal ──────────────────────────────────────────

export async function fetchExpertReport(token: string): Promise<AssessmentReport> {
  const res = await fetch(`/api/review/expert/${token}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Expert report fetch failed (${res.status})`);
  return (await res.json()) as AssessmentReport;
}

export async function submitExpertReview(
  token: string,
  payload: ExpertReviewPayload,
): Promise<ReviewSaveResponse> {
  const res = await fetch(`/api/review/expert/${token}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Expert submit failed (${res.status})`);
  return (await res.json()) as ReviewSaveResponse;
}

export async function fetchSupervisorReport(token: string): Promise<AssessmentReport> {
  const res = await fetch(`/api/review/supervisor/${token}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Supervisor report fetch failed (${res.status})`);
  return (await res.json()) as AssessmentReport;
}

export async function submitSupervisorReview(
  token: string,
  payload: SupervisorReviewPayload,
): Promise<ReviewSaveResponse> {
  const res = await fetch(`/api/review/supervisor/${token}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Supervisor submit failed (${res.status})`);
  return (await res.json()) as ReviewSaveResponse;
}

export async function listEnrichedSessions(
  query: { search?: string; limit?: number; offset?: number } = {},
): Promise<AdminSessionSummary[]> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const url = `/api/admin/sessions/enriched${params.size ? `?${params}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Enriched sessions failed (${res.status})`);
  return (await res.json()) as AdminSessionSummary[];
}

export async function fetchAdminStats(): Promise<AdminStats> {
  const res = await fetch("/api/admin/stats", { cache: "no-store" });
  if (!res.ok) throw new Error(`Stats failed (${res.status})`);
  return (await res.json()) as AdminStats;
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
