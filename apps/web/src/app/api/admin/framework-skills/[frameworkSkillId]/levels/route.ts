import { NextResponse, type NextRequest } from "next/server";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

const BASE = () => process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";

export async function POST(
  request: NextRequest,
  { params }: { params: { frameworkSkillId: string } },
) {
  const body = (await request.json()) as {
    id?: string | null;
    level?: number | null;
    content: string;
  };
  const upstream = await fetch(
    `${BASE()}/api/v1/admin/framework-skills/${encodeURIComponent(params.frameworkSkillId)}/levels`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...voiceEngineAdminHeaders(request) },
      body: JSON.stringify({
        id: body.id ?? null,
        level: body.level ?? null,
        content: body.content,
      }),
    },
  );
  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  return NextResponse.json({
    id: data.id,
    level: data.level,
    content: data.content,
  });
}
