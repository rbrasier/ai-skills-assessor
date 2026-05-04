import { NextResponse, type NextRequest } from "next/server";
import { mapVoiceEngineClaim, mapVoiceEngineReport } from "@/lib/map-assessment-report";

export const dynamic = "force-dynamic";

const VOICE_ENGINE = () => process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";

export async function GET(
  _req: NextRequest,
  { params }: { params: { token: string } },
) {
  const upstream = await fetch(
    `${VOICE_ENGINE()}/api/v1/review/expert/${params.token}`,
    { cache: "no-store" },
  );
  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });
  return NextResponse.json(mapVoiceEngineReport(data));
}

export async function PUT(
  req: NextRequest,
  { params }: { params: { token: string } },
) {
  const body = (await req.json()) as {
    reviewerFullName: string;
    reviewerEmail: string;
    claims: Array<{ id: string; expertLevel: number }>;
  };

  const upstream = await fetch(
    `${VOICE_ENGINE()}/api/v1/review/expert/${params.token}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewer_full_name: body.reviewerFullName,
        reviewer_email: body.reviewerEmail,
        claims: body.claims.map((c) => ({ id: c.id, expert_level: c.expertLevel })),
      }),
    },
  );

  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });

  const claims = Array.isArray(data.claims)
    ? data.claims.map((c: Record<string, unknown>) => mapVoiceEngineClaim(c))
    : [];

  return NextResponse.json({
    sessionId: data.session_id,
    reportStatus: data.report_status,
    reviewsCompletedAt: data.reviews_completed_at ?? null,
    claims,
  });
}
