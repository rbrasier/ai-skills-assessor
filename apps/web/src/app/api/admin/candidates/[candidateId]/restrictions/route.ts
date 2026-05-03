import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: { candidateId: string } },
) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const upstream = await fetch(
    `${voiceEngineUrl}/api/v1/admin/candidates/${encodeURIComponent(params.candidateId)}/restrictions`,
  );
  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}

export async function POST(
  request: Request,
  { params }: { params: { candidateId: string } },
) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const body = await request.json();
  const upstream = await fetch(
    `${voiceEngineUrl}/api/v1/admin/candidates/${encodeURIComponent(params.candidateId)}/override`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        granted_by: body.grantedBy,
        expires_in_days: body.expiresInDays ?? 7,
        reason: body.reason ?? null,
      }),
    },
  );
  if (!upstream.ok) {
    const err = await upstream.json().catch(() => ({}));
    return NextResponse.json(err, { status: upstream.status });
  }
  return new NextResponse(null, { status: 204 });
}

export async function DELETE(
  request: Request,
  { params }: { params: { candidateId: string } },
) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const { searchParams } = new URL(request.url);
  const revokedBy = searchParams.get("revokedBy") ?? "admin";
  const upstream = await fetch(
    `${voiceEngineUrl}/api/v1/admin/candidates/${encodeURIComponent(params.candidateId)}/override?revoked_by=${encodeURIComponent(revokedBy)}`,
    { method: "DELETE" },
  );
  if (!upstream.ok) {
    return NextResponse.json({}, { status: upstream.status });
  }
  return new NextResponse(null, { status: 204 });
}
