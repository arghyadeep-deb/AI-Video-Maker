import { NextRequest, NextResponse } from "next/server";

// specs/04-tasks/task-14-auth-accounts.md: "redirect-when-unauthenticated".
// This is a presence-only check (the session cookie is httponly, so
// client JS can't read it, but Next's proxy runs server-side and can) -
// it doesn't validate the JWT signature itself (that would need sharing
// JWT_SECRET with the frontend for no real benefit, since every actual API
// call already re-validates the session and redirects on 401 via
// lib/api.ts's handleResponse). This just avoids a flash of broken UI for
// the common case: never logged in at all.
//
// Named "proxy" (not "middleware") per Next.js 16's renamed file
// convention - this project's Next.js version deprecated "middleware.ts"
// in favor of "proxy.ts" (same mechanism, same execution point).
const SESSION_COOKIE_NAME = "session";
const PUBLIC_PATHS = ["/login"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Everything except Next's internals and static assets.
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
