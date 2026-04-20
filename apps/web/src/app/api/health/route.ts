import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const WEB_VERSION = "0.4.1";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    version: WEB_VERSION,
  });
}
