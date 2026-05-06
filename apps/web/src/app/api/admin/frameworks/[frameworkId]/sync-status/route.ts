import { NextResponse, type NextRequest } from "next/server";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

const BASE = () => process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: { frameworkId: string } },
): Promise<NextResponse> {
  const upstream = await fetch(
    `${BASE()}/api/v1/admin/frameworks/${encodeURIComponent(params.frameworkId)}/sync-status`,
    { cache: "no-store", headers: voiceEngineAdminHeaders(request) },
  );
  const data = (await upstream.json()) as unknown;
  return NextResponse.json(data, { status: upstream.status });
}
