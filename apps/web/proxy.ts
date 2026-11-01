import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

// Next 16 renamed middleware.ts to proxy.ts; same feature, Node runtime.
// Everything the matcher reaches needs a session unless listed here.
const PUBLIC_PATHS = ["/login", "/register"];
// Pages in app/(curator) plus the curator API.
const CURATOR_PREFIXES = ["/review", "/sources", "/api/curator"];

function matches(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export const proxy = auth((req) => {
  const { pathname, search } = req.nextUrl;
  const user = req.auth?.user;
  const isApi = pathname.startsWith("/api/");

  if (matches(pathname, PUBLIC_PATHS)) {
    // Already signed in: skip the login/register forms.
    return user ? NextResponse.redirect(new URL("/", req.nextUrl)) : NextResponse.next();
  }

  if (!user) {
    if (isApi) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    const login = new URL("/login", req.nextUrl);
    login.searchParams.set("callbackUrl", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }

  if (matches(pathname, CURATOR_PREFIXES) && user.role !== "curator") {
    if (isApi) return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    return NextResponse.redirect(new URL("/", req.nextUrl));
  }

  return NextResponse.next();
});

export const config = {
  // Skip Auth.js's own routes, Next internals, and static files.
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
