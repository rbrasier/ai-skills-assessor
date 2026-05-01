import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const search = request.nextUrl.searchParams.toString();
  const url = `${voiceEngineUrl}/api/v1/admin/sessions/enriched${search ? `?${search}` : ""}`;

  const upstream = await fetch(url, { cache: "no-store" });
  const data = (await upstream.json()) as unknown;
  if (!upstream.ok) {
    return NextResponse.json(data, { status: upstream.status });
  }

  if (!Array.isArray(data)) return NextResponse.json(data, { status: upstream.status });

  const mapped = data.map((s: Record<string, unknown>) => ({
    sessionId: s.session_id,
    candidateEmail: s.candidate_email,
    phoneNumber: s.phone_number,
    status: s.status,
    durationSeconds: s.duration_seconds,
    createdAt: s.created_at,
    startedAt: s.started_at ?? null,
    endedAt: s.ended_at ?? null,
    candidateName: s.candidate_name ?? null,
    reportStatus: s.report_status ?? null,
    expertReviewToken: s.expert_review_token ?? null,
    supervisorReviewToken: s.supervisor_review_token ?? null,
    maxSfiaLevel: s.max_sfia_level ?? null,
    overallConfidence: s.overall_confidence ?? null,
    topSkillCodes: Array.isArray(s.top_skill_codes) ? s.top_skill_codes : [],
  }));

  return NextResponse.json(mapped);
}
