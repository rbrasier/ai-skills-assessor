import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: { sessionId: string } },
) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const upstream = await fetch(
    `${voiceEngineUrl}/api/v1/assessment/${encodeURIComponent(params.sessionId)}/status`,
    { cache: "no-store" },
  );
  const data = await upstream.json();
  if (!upstream.ok) {
    return NextResponse.json(data, { status: upstream.status });
  }
  return NextResponse.json(
    {
      sessionId: data.session_id,
      status: data.status,
      durationSeconds: data.duration_seconds,
      startedAt: data.started_at,
      endedAt: data.ended_at,
      failureReason: data.failure_reason,
      dialingMethod: data.dialing_method ?? "daily",
      browserJoinUrl: data.browser_join_url ?? null,
    },
    { status: upstream.status },
  );
}
