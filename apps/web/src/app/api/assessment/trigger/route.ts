import { NextResponse, type NextRequest } from "next/server";

import type {
  AssessmentTriggerRequest,
  AssessmentTriggerResponse,
} from "@ai-skills-assessor/shared-types";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  let body: AssessmentTriggerRequest;
  try {
    body = (await request.json()) as AssessmentTriggerRequest;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { phoneNumber, candidateId } = body ?? {};
  if (!phoneNumber || !candidateId) {
    return NextResponse.json(
      { error: "phoneNumber and candidateId are required" },
      { status: 400 },
    );
  }

  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";

  const upstream = await fetch(`${voiceEngineUrl}/api/v1/assessment/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone_number: phoneNumber, candidate_id: candidateId }),
  });

  const data = (await upstream.json()) as AssessmentTriggerResponse;
  return NextResponse.json(data, { status: upstream.status });
}
