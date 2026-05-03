import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const upstream = await fetch(`${voiceEngineUrl}/api/v1/admin/settings`);
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}

export async function PUT(request: Request) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const body = await request.json();
  const upstream = await fetch(`${voiceEngineUrl}/api/v1/admin/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      cooldown_days: body.cooldownDays,
      updated_by: body.updatedBy ?? null,
    }),
  });
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
