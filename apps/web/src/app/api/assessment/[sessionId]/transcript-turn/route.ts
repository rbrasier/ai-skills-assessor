import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: { sessionId: string } },
) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const body = await request.json();
  const upstream = await fetch(
    `${voiceEngineUrl}/api/v1/assessment/${encodeURIComponent(params.sessionId)}/transcript-turn`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        timestamp: body.timestamp,
        speaker: body.speaker,
        text: body.text,
        phase: body.phase,
        vad_confidence: body.vadConfidence ?? null,
      }),
    },
  );
  if (!upstream.ok) {
    return NextResponse.json({}, { status: upstream.status });
  }
  return new NextResponse(null, { status: 204 });
}
