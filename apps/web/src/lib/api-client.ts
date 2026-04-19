import type {
  AssessmentTriggerRequest,
  AssessmentTriggerResponse,
} from "@ai-skills-assessor/shared-types";

/**
 * Thin client for triggering an assessment via the local Next.js API route.
 * The route in turn forwards to the Python voice engine. UI components should
 * use this helper rather than calling `fetch` directly so that we have a single
 * place to add auth headers, retries, and telemetry later.
 */
export async function triggerAssessment(
  payload: AssessmentTriggerRequest,
): Promise<AssessmentTriggerResponse> {
  const response = await fetch("/api/assessment/trigger", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Failed to trigger assessment (${response.status})`);
  }

  return (await response.json()) as AssessmentTriggerResponse;
}
