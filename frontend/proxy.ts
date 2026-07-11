import { NextRequest, NextResponse } from "next/server";

// specs/04-tasks/task-14-auth-accounts.md: "redirect-when-unauthenticated".
//
// This used to also do a server-side cookie-presence check here (Next's
// proxy runs server-side, so it COULD read a non-httponly-to-JS cookie).
// Removed 2026-07-11 after a live deploy proved it fundamentally broken:
// the session cookie is set by the BACKEND's origin (e.g. a Cloudflare
// tunnel domain), not the frontend's (Vercel) - browsers never attach a
// cookie to a domain other than the one that set it, so
// `request.cookies.has("session")` here can NEVER see it whenever
// frontend and backend are on different domains. That's not a config bug
// to fix - it's this project's actual intended production topology (Vercel
// frontend + a separately-hosted backend), so the check would 307-redirect
// every single logged-in user straight back to /login, forever.
//
// The redirect-when-unauthenticated requirement is still fully met by
// lib/api.ts's handleResponse: every real API call re-validates the
// session (the cookie IS correctly sent cross-origin to the backend that
// owns it, via fetch's credentials:'include') and redirects to /login on
// any 401. That client-side path doesn't care what domain the cookie
// lives on, so it works in every topology - same-origin or not - and is
// the only mechanism this app relies on now.
//
// Named "proxy" (not "middleware") per Next.js 16's renamed file
// convention - this project's Next.js version deprecated "middleware.ts"
// in favor of "proxy.ts" (same mechanism, same execution point). Kept as
// a real (if currently empty) hook rather than deleting the file, since
// the matcher/config wiring stays useful if a future same-origin deploy
// ever wants a genuine server-side check back.
export function proxy(_request: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: [
    // Everything except Next's internals and static assets.
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
