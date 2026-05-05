import { NextResponse, type NextRequest } from "next/server";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

const BASE = () => process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: { frameworkId: string } },
) {
  const upstream = await fetch(
    `${BASE()}/api/v1/admin/frameworks/${encodeURIComponent(params.frameworkId)}/skills`,
    { cache: "no-store", headers: voiceEngineAdminHeaders(request) },
  );
  const data = (await upstream.json()) as unknown;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  if (!Array.isArray(data)) return NextResponse.json(data, { status: upstream.status });
  const mapped = data.map((s: Record<string, unknown>) => ({
    id: s.id,
    skillCode: s.skill_code,
    skillName: s.skill_name,
    category: s.category,
    subcategory: s.subcategory ?? null,
    description: s.description,
    guidance: s.guidance ?? null,
    levels: Array.isArray(s.levels)
      ? s.levels.map((lv: Record<string, unknown>) => ({
          id: lv.id,
          level: lv.level ?? null,
          content: lv.content,
        }))
      : [],
  }));
  return NextResponse.json(mapped);
}

export async function POST(
  request: NextRequest,
  { params }: { params: { frameworkId: string } },
) {
  const body = (await request.json()) as {
    id?: string | null;
    skillCode: string;
    skillName: string;
    category?: string;
    subcategory?: string | null;
    description?: string;
    guidance?: string | null;
  };
  const upstream = await fetch(
    `${BASE()}/api/v1/admin/frameworks/${encodeURIComponent(params.frameworkId)}/skills`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...voiceEngineAdminHeaders(request) },
      body: JSON.stringify({
        id: body.id ?? null,
        skill_code: body.skillCode,
        skill_name: body.skillName,
        category: body.category ?? "General",
        subcategory: body.subcategory ?? null,
        description: body.description ?? "",
        guidance: body.guidance ?? null,
      }),
    },
  );
  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  return NextResponse.json({
    id: data.id,
    skillCode: data.skill_code,
    skillName: data.skill_name,
    category: data.category,
    subcategory: data.subcategory,
    description: data.description,
    guidance: data.guidance,
  });
}
