import { NextResponse, type NextRequest } from "next/server";
import { voiceEngineAdminHeaders } from "@/lib/voice-engine-admin";

export const dynamic = "force-dynamic";

const upstream = (request: NextRequest) =>
  `${process.env.VOICE_ENGINE_URL ?? "http://localhost:8000"}/api/v1/admin/site-config`;

export async function GET(request: NextRequest) {
  const res = await fetch(upstream(request), {
    headers: voiceEngineAdminHeaders(request),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function PATCH(request: NextRequest) {
  const body = await request.json();
  const res = await fetch(upstream(request), {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...voiceEngineAdminHeaders(request),
    },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
