import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const dialingMethod = process.env.NEXT_PUBLIC_DIALING_METHOD || "browser";

  return NextResponse.json({
    dialingMethod,
  });
}
