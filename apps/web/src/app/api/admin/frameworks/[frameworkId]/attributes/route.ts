import { NextResponse, type NextRequest } from "next/server";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

const BASE = () => process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: { frameworkId: string } },
) {
  const upstream = await fetch(
    `${BASE()}/api/v1/admin/frameworks/${encodeURIComponent(params.frameworkId)}/attributes`,
    { cache: "no-store", headers: voiceEngineAdminHeaders(request) },
  );
  const data = (await upstream.json()) as unknown;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  if (!Array.isArray(data)) return NextResponse.json(data, { status: upstream.status });
  const mapped = data.map((a: Record<string, unknown>) => ({
    id: a.id,
    attribute: a.attribute,
    level: a.level,
    description: a.description,
  }));
  return NextResponse.json(mapped);
}

export async function POST(
  request: NextRequest,
  { params }: { params: { frameworkId: string } },
) {
  const body = (await request.json()) as {
    id?: string | null;
    attribute: string;
    level: number;
    description: string;
  };
  const upstream = await fetch(
    `${BASE()}/api/v1/admin/frameworks/${encodeURIComponent(params.frameworkId)}/attributes`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...voiceEngineAdminHeaders(request) },
      body: JSON.stringify({
        id: body.id ?? null,
        attribute: body.attribute,
        level: body.level,
        description: body.description,
      }),
    },
  );
  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  return NextResponse.json({
    id: data.id,
    attribute: data.attribute,
    level: data.level,
    description: data.description,
  });
}
