import type { NextRequest } from "next/server";

/** Headers for voice-engine routes gated by ``ADMIN_TOKEN`` + ``X-Admin-Token``. */
export function voiceEngineAdminHeaders(request?: NextRequest): HeadersInit {
  const fromCookie = request?.cookies.get("admin_session")?.value;
  const fromEnv = process.env.ADMIN_TOKEN;
  const token = (fromCookie || fromEnv || "").trim();
  return token ? { "X-Admin-Token": token } : {};
}
