import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export const SESSION_COOKIE = "news_admin_session";
export const CSRF_COOKIE = "news_admin_csrf";

interface SessionInfo {
  actor: string;
  permissions: string[];
  auth_method: string;
  mfa_verified: boolean;
}

export async function requireSession(): Promise<SessionInfo> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) redirect("/admin/login");
  const response = await fetch(`${siteApiUrl()}/api/v1/auth/session`, {
    headers: { "X-Admin-Session": token },
    cache: "no-store",
  });
  if (!response.ok) redirect("/admin/login");
  return (await response.json()) as SessionInfo;
}

export function siteApiUrl(): string {
  return process.env.SITE_API_URL ?? "http://localhost:8002";
}
