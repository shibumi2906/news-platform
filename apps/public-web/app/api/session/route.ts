import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { CSRF_COOKIE, SESSION_COOKIE, siteApiUrl } from "@/lib/session";
import { isSameOrigin } from "@/lib/same-origin";

export async function POST(request: Request) {
  if (!isSameOrigin(request)) return NextResponse.json({ error: "cross-site request rejected" }, { status: 403 });
  const form = await request.formData();
  const cookieStore = await cookies();
  if (form.get("action") === "logout") {
    const token = cookieStore.get(SESSION_COOKIE)?.value;
    const csrf = cookieStore.get(CSRF_COOKIE)?.value;
    if (token && csrf) {
      await fetch(`${siteApiUrl()}/api/v1/auth/logout`, {
        method: "POST",
        headers: { "X-Admin-Session": token, "X-CSRF-Token": csrf },
      }).catch(() => undefined);
    }
    cookieStore.delete(SESSION_COOKIE);
    cookieStore.delete(CSRF_COOKIE);
    return NextResponse.redirect(publicDestination("/admin/login", request), 303);
  }
  const response = await fetch(`${siteApiUrl()}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: String(form.get("username") ?? ""), password: String(form.get("password") ?? "") }),
    cache: "no-store",
  });
  if (!response.ok) return NextResponse.redirect(publicDestination("/admin/login?error=invalid", request), 303);
  const payload = await response.json() as { session_token: string; csrf_token: string; expires_in: number };
  const result = NextResponse.redirect(publicDestination("/admin", request), 303);
  const secure = process.env.SESSION_COOKIE_SECURE === "true";
  result.cookies.set(SESSION_COOKIE, payload.session_token, { httpOnly: true, sameSite: "strict", secure, path: "/", maxAge: payload.expires_in });
  result.cookies.set(CSRF_COOKIE, payload.csrf_token, { httpOnly: false, sameSite: "strict", secure, path: "/", maxAge: payload.expires_in });
  return result;
}

function publicDestination(path: string, request: Request): URL {
  return new URL(path, process.env.NEXT_PUBLIC_WEB_URL ?? request.url);
}
