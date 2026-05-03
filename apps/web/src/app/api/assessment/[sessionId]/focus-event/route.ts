import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: { sessionId: string } },
) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const body = await request.json();
  const upstream = await fetch(
    `${voiceEngineUrl}/api/v1/assessment/${encodeURIComponent(params.sessionId)}/focus-event`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phase: body.phase, duration_ms: body.durationMs }),
    },
  );
  if (!upstream.ok) {
    return NextResponse.json({}, { status: upstream.status });
  }
  return new NextResponse(null, { status: 204 });
}
