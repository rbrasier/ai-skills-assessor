import { NextResponse, type NextRequest } from "next/server";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

const BASE = () => process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const upstream = await fetch(`${BASE()}/api/v1/admin/frameworks`, {
    cache: "no-store",
    headers: voiceEngineAdminHeaders(request),
  });
  const data = (await upstream.json()) as unknown;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  if (!Array.isArray(data)) return NextResponse.json(data, { status: upstream.status });
  const mapped = data.map((f: Record<string, unknown>) => ({
    id: f.id,
    type: f.type,
    version: f.version,
    name: f.name,
    rubric: f.rubric,
    isActive: f.is_active ?? true,
  }));
  return NextResponse.json(mapped);
}

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    id?: string | null;
    type: string;
    version: string;
    name: string;
    rubric?: string;
    isActive?: boolean;
  };
  const upstream = await fetch(`${BASE()}/api/v1/admin/frameworks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...voiceEngineAdminHeaders(request) },
    body: JSON.stringify({
      id: body.id ?? null,
      type: body.type,
      version: body.version,
      name: body.name,
      rubric: body.rubric ?? "",
      is_active: body.isActive ?? true,
    }),
  });
  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  return NextResponse.json({
    id: data.id,
    type: data.type,
    version: data.version,
    name: data.name,
    rubric: data.rubric,
    isActive: data.is_active ?? true,
  });
}
