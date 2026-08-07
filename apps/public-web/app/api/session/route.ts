import { createHash, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { createSessionToken, SESSION_COOKIE } from "@/lib/session-token";

export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "cross-site request rejected" }, { status: 403 });
  const form = await request.formData();
  if (form.get("action") === "logout") {
    (await cookies()).delete(SESSION_COOKIE);
    return NextResponse.redirect(publicDestination("/admin/login", request), 303);
  }
  const username = String(form.get("username") ?? "");
  const password = String(form.get("password") ?? "");
  const configuredUser = process.env.ADMIN_USERNAME;
  const configuredPassword = process.env.ADMIN_PASSWORD;
  const secret = process.env.SESSION_SECRET;
  if (!configuredUser || !configuredPassword || !secret) {
    return NextResponse.json({ error: "admin session is not configured" }, { status: 503 });
  }
  if (!safeEqual(username, configuredUser) || !safeEqual(password, configuredPassword)) {
    return NextResponse.redirect(publicDestination("/admin/login?error=invalid", request), 303);
  }
  const response = NextResponse.redirect(publicDestination("/admin", request), 303);
  response.cookies.set(SESSION_COOKIE, createSessionToken(username, secret), {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.SESSION_COOKIE_SECURE === "true",
    path: "/",
    maxAge: 8 * 60 * 60,
  });
  return response;
}

function safeEqual(left: string, right: string): boolean {
  const leftHash = createHash("sha256").update(left).digest();
  const rightHash = createHash("sha256").update(right).digest();
  return timingSafeEqual(leftHash, rightHash);
}

function sameOrigin(request: Request): boolean {
  if (request.headers.get("sec-fetch-site") === "cross-site") return false;
  const origin = request.headers.get("origin");
  return origin === null || origin === new URL(request.url).origin;
}

function publicDestination(path: string, request: Request): URL {
  return new URL(path, process.env.NEXT_PUBLIC_WEB_URL ?? request.url);
}
