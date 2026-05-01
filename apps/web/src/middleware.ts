import { NextResponse, type NextRequest } from "next/server";

const COOKIE_NAME = "admin_session";
const PROTECTED = ["/dashboard"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const needsAuth = PROTECTED.some((p) => pathname === p || pathname.startsWith(p + "/"));
  if (!needsAuth) return NextResponse.next();

  const cookie = request.cookies.get(COOKIE_NAME);
  const adminToken = process.env.ADMIN_TOKEN;

  if (!cookie || !adminToken || cookie.value !== adminToken) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
