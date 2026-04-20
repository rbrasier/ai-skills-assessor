import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const search = request.nextUrl.searchParams.toString();
  const url = `${voiceEngineUrl}/api/v1/admin/sessions${search ? `?${search}` : ""}`;

  const upstream = await fetch(url, { cache: "no-store" });
  const data = await upstream.json();
  if (!upstream.ok) {
    return NextResponse.json(data, { status: upstream.status });
  }

  const mapped = Array.isArray(data)
    ? data.map((s: Record<string, unknown>) => ({
        sessionId: s.session_id,
        candidateEmail: s.candidate_email,
        phoneNumber: s.phone_number,
        status: s.status,
        durationSeconds: s.duration_seconds,
        createdAt: s.created_at,
        startedAt: s.started_at,
        endedAt: s.ended_at,
      }))
    : data;

  return NextResponse.json(mapped, { status: upstream.status });
}
