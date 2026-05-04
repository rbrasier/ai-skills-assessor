import { NextResponse, type NextRequest } from "next/server";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

export async function PUT(
  request: NextRequest,
  { params }: { params: { sessionId: string } },
) {
  const body = (await request.json()) as {
    adminActor: string;
    claims: Array<{ id: string; adminDecision?: "verified" | "rejected" | "flagged"; adminComment?: string }>;
  };

  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const upstream = await fetch(
    `${voiceEngineUrl}/api/v1/admin/sessions/${encodeURIComponent(params.sessionId)}/claims`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...voiceEngineAdminHeaders(request),
      },
      body: JSON.stringify({
        admin_actor: body.adminActor,
        claims: body.claims.map((c) => ({
          id: c.id,
          admin_decision: c.adminDecision,
          admin_comment: c.adminComment,
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
      }))
    : [];

  return NextResponse.json({
    sessionId: data.session_id,
    reportStatus: data.report_status,
    reviewsCompletedAt: data.reviews_completed_at ?? null,
    claims,
  });
}
