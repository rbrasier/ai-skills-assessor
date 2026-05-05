import { NextResponse, type NextRequest } from "next/server";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

function mapClaim(c: Record<string, unknown>) {
  return {
    id: c.id,
    sessionId: c.session_id,
    verbatimQuote: c.verbatim_quote,
    interpretedClaim: c.interpreted_claim,
    summary: c.summary ?? "",
    claimType: c.claim_type ?? "sme",
    skillCode: c.sfia_skill_code ?? c.skill_code,
    skillName: c.sfia_skill_name ?? c.skill_name,
    level: typeof c.sfia_level === "number" ? c.sfia_level : (c.level ?? 0),
    confidence: c.confidence ?? 0,
    reasoning: c.reasoning,
    expertLevel: c.expert_level ?? null,
    supervisorDecision: c.supervisor_decision ?? null,
    supervisorComment: c.supervisor_comment ?? null,
    adminDecision: c.admin_decision ?? null,
    adminComment: c.admin_comment ?? null,
    adminActor: c.admin_actor ?? null,
    adminUpdatedAt: c.admin_updated_at ?? null,
  };
}

function mapReport(raw: Record<string, unknown>) {
  const claims = Array.isArray(raw.claims_json)
    ? raw.claims_json.map((c: Record<string, unknown>) => mapClaim(c))
    : [];

  const holistic = Array.isArray(raw.holistic_assessment_json)
    ? raw.holistic_assessment_json.map((h: Record<string, unknown>) => ({
        skillCode: h.skill_code,
        skillName: h.skill_name,
        estimatedLevel: h.estimated_level,
        prominence: h.prominence,
        evidenceSummary: h.evidence_summary,
      }))
    : [];

  return {
    sessionId: raw.session_id,
    candidateName: raw.candidate_name ?? null,
    expertReviewToken: raw.expert_review_token ?? null,
    supervisorReviewToken: raw.supervisor_review_token ?? null,
    overallConfidence: raw.overall_confidence ?? null,
    reportStatus: raw.report_status ?? null,
    claimsJson: claims,
    holisticAssessmentJson: holistic,
    transcriptJson: raw.transcript_json ?? null,
    reportGeneratedAt: raw.report_generated_at ?? null,
    expiresAt: raw.expires_at ?? null,
    expertSubmittedAt: raw.expert_submitted_at ?? null,
    expertReviewerName: raw.expert_reviewer_name ?? null,
    expertReviewerEmail: raw.expert_reviewer_email ?? null,
    supervisorSubmittedAt: raw.supervisor_submitted_at ?? null,
    supervisorReviewerName: raw.supervisor_reviewer_name ?? null,
    supervisorReviewerEmail: raw.supervisor_reviewer_email ?? null,
    reviewsCompletedAt: raw.reviews_completed_at ?? null,
  };
}

export async function GET(
  request: NextRequest,
  { params }: { params: { sessionId: string } },
) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const upstream = await fetch(
    `${voiceEngineUrl}/api/v1/admin/sessions/${encodeURIComponent(params.sessionId)}/report`,
    { cache: "no-store", headers: voiceEngineAdminHeaders(request) },
  );
  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  return NextResponse.json(mapReport(data));
}
