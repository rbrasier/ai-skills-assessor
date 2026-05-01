import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(_req: NextRequest) {
  const voiceEngineUrl = process.env.VOICE_ENGINE_URL ?? "http://localhost:8000";
  const upstream = await fetch(`${voiceEngineUrl}/api/v1/admin/stats`, {
    cache: "no-store",
  });
  const data = (await upstream.json()) as Record<string, unknown>;
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });

  return NextResponse.json({
    totalCalls: data.total_calls,
    avgDurationMinutes: data.avg_duration_minutes,
    completionRatePct: data.completion_rate_pct,
    awaitingReviewCount: data.awaiting_review_count,
    avgSfiaLevel: data.avg_sfia_level,
    callsPerDay: data.calls_per_day,
    outcomeBuckets: data.outcome_buckets,
  });
}
