import { NextResponse, type NextRequest } from "next/server";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

export async function PATCH(
  request: NextRequest,
  { params }: { params: { candidateId: string } },
) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const body = (await request.json()) as { enabled: boolean; updatedBy: string };
  const upstream = await fetch(
    `${voiceEngineUrl}/api/v1/admin/candidates/${encodeURIComponent(params.candidateId)}/no-restrictions`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...voiceEngineAdminHeaders(request),
      },
      body: JSON.stringify({
        enabled: body.enabled,
        updated_by: body.updatedBy,
      }),
    },
  );
  if (!upstream.ok) {
    const err = await upstream.json().catch(() => ({}));
    return NextResponse.json(err, { status: upstream.status });
  }
  return new NextResponse(null, { status: 204 });
}
