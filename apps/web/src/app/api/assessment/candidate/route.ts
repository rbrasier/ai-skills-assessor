import { NextResponse, type NextRequest } from "next/server";

import type { CandidateRequest } from "@ai-skills-assessor/shared-types";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  let body: CandidateRequest;
  try {
    body = (await request.json()) as CandidateRequest;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const upstream = await fetch(`${voiceEngineUrl}/api/v1/assessment/candidate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      work_email: body.workEmail,
      first_name: body.firstName,
      last_name: body.lastName,
      employee_id: body.employeeId,
    }),
  });

  if (!upstream.ok) {
    const errorText = await upstream.text();
    return NextResponse.json(
      { error: `Voice engine error: ${errorText}` },
      { status: upstream.status },
    );
  }

  const data = await upstream.json();
  return NextResponse.json(
    {
      candidateId: data.candidate_id,
      workEmail: data.work_email,
      firstName: data.first_name,
      lastName: data.last_name,
    },
    { status: upstream.status },
  );
}
