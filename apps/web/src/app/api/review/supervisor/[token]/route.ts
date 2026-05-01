import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const VOICE_ENGINE = () => process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";

function mapReport(raw: Record<string, unknown>) {
  const claims = Array.isArray(raw.claims_json)
    ? raw.claims_json.map((c: Record<string, unknown>) => ({
        id: c.id,
        sessionId: c.session_id,
        verbatimQuote: c.verbatim_quote,
        interpretedClaim: c.interpreted_claim,
        skillCode: c.skill_code,
        skillName: c.skill_name,
        level: c.level,
        confidence: c.confidence,
        reasoning: c.reasoning,
        expertLevel: c.expert_level ?? null,
        supervisorDecision: c.supervisor_decision ?? null,
        supervisorComment: c.supervisor_comment ?? null,
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
  _req: NextRequest,
  { params }: { params: { token: string } },
) {
  const upstream = await fetch(
    `${VOICE_ENGINE()}/api/v1/review/supervisor/${params.token}`,
    { cache: "no-store" },
  );
  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  return NextResponse.json(mapReport(data));
}

export async function PUT(
  req: NextRequest,
  { params }: { params: { token: string } },
) {
  const body = (await req.json()) as {
    reviewerFullName: string;
    reviewerEmail: string;
    claims: Array<{
      id: string;
      supervisorDecision: "verified" | "rejected";
      supervisorComment?: string;
    }>;
  };

  const upstream = await fetch(
    `${VOICE_ENGINE()}/api/v1/review/supervisor/${params.token}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewer_full_name: body.reviewerFullName,
        reviewer_email: body.reviewerEmail,
        claims: body.claims.map((c) => ({
          id: c.id,
          supervisor_decision: c.supervisorDecision,
          supervisor_comment: c.supervisorComment?.trim() || "",
        })),
      }),
    },
  );

  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });

  const claims = Array.isArray(data.claims)
    ? data.claims.map((c: Record<string, unknown>) => ({
        id: c.id,
        sessionId: c.session_id,
        verbatimQuote: c.verbatim_quote,
        interpretedClaim: c.interpreted_claim,
        skillCode: c.skill_code,
        skillName: c.skill_name,
        level: c.level,
        confidence: c.confidence,
        reasoning: c.reasoning,
        expertLevel: c.expert_level ?? null,
        supervisorDecision: c.supervisor_decision ?? null,
        supervisorComment: c.supervisor_comment ?? null,
      }))
    : [];

  return NextResponse.json({
    sessionId: data.session_id,
    reportStatus: data.report_status,
    reviewsCompletedAt: data.reviews_completed_at ?? null,
    claims,
  });
}
