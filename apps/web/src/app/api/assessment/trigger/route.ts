import { NextResponse, type NextRequest } from "next/server";

import type { TriggerCallRequest } from "@ai-skills-assessor/shared-types";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  let body: TriggerCallRequest;
  try {
    body = (await request.json()) as TriggerCallRequest;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { phoneNumber, candidateId, dialingMethod } = body ?? {};
  if (!candidateId) {
    return NextResponse.json(
      { error: "candidateId is required" },
      { status: 400 },
    );
  }
  // Phone number is required for PSTN dialing, but not for browser dialing
  if (dialingMethod !== "browser" && !phoneNumber) {
    return NextResponse.json(
      { error: "phoneNumber is required for PSTN dialing" },
      { status: 400 },
    );
  }

  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";

  const upstreamBody: Record<string, unknown> = { candidate_id: candidateId };
  if (phoneNumber) {
    upstreamBody.phone_number = phoneNumber;
  }
  if (dialingMethod) {
    upstreamBody.dialing_method = dialingMethod;
  }

  const upstream = await fetch(`${voiceEngineUrl}/api/v1/assessment/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(upstreamBody),
  });

  const data = await upstream.json();
  if (!upstream.ok) {
    return NextResponse.json(data, { status: upstream.status });
  }
  return NextResponse.json(
    { sessionId: data.session_id, status: data.status },
    { status: upstream.status },
  );
}
