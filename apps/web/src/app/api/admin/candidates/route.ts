import { NextResponse, type NextRequest } from "next/server";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

function mapSession(s: Record<string, unknown>) {
  return {
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
    terminationReason: s.termination_reason ?? null,
    focusSuspicious: Boolean(s.focus_suspicious ?? false),
    totalFocusAwayMs: Number(s.total_focus_away_ms ?? 0),
  };
}

export async function GET(request: NextRequest) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const qs = request.nextUrl.searchParams.toString();
  const url = `${voiceEngineUrl}/api/v1/admin/candidates${qs ? `?${qs}` : ""}`;
  const upstream = await fetch(url, {
    cache: "no-store",
    headers: voiceEngineAdminHeaders(request),
  });
  const data = (await upstream.json()) as unknown;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  if (!Array.isArray(data)) return NextResponse.json(data, { status: upstream.status });

  const mapped = data.map((row: Record<string, unknown>) => ({
    email: row.email,
    firstName: row.first_name,
    lastName: row.last_name,
    totalCalls: row.total_calls,
    lastCallAt: row.last_call_at ?? null,
    sessions: Array.isArray(row.sessions)
      ? row.sessions.map((s: Record<string, unknown>) => mapSession(s))
      : [],
  }));

  return NextResponse.json(mapped);
}
