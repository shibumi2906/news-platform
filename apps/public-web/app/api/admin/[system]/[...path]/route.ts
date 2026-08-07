import { cookies } from "next/headers";
import { backendUrl } from "@/lib/api";
import { CSRF_COOKIE, SESSION_COOKIE, siteApiUrl } from "@/lib/session";
import { isSameOrigin } from "@/lib/same-origin";

type Context = { params: Promise<{ system: string; path: string[] }> };
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;

async function proxy(request: Request, context: Context): Promise<Response> {
  if (!isSameOrigin(request)) return Response.json({ error: "cross-site request rejected" }, { status: 403 });
  const cookieStore = await cookies();
  const session = cookieStore.get(SESSION_COOKIE)?.value;
  const csrf = cookieStore.get(CSRF_COOKIE)?.value;
  if (!session) return Response.json({ error: "authentication required" }, { status: 401 });
  const introspection = await fetch(`${siteApiUrl()}/api/v1/auth/session`, {
    headers: { "X-Admin-Session": session }, cache: "no-store",
  });
  if (!introspection.ok) return Response.json({ error: "session expired" }, { status: 401 });
  if (!SAFE_METHODS.has(request.method) && (!csrf || request.headers.get("x-csrf-token") !== csrf)) {
    return Response.json({ error: "CSRF validation failed" }, { status: 403 });
  }
  const { system, path } = await context.params;
  if (system !== "site" && system !== "integrator") return Response.json({ error: "unknown backend" }, { status: 404 });
  if (path.some((segment) => !/^[A-Za-z0-9._~-]+$/.test(segment))) return Response.json({ error: "invalid backend path" }, { status: 400 });
  const sourceUrl = new URL(request.url);
  const target = `${backendUrl(system)}/${path.join("/")}${sourceUrl.search}`;
  const headers = new Headers({ "X-Admin-Session": session });
  if (csrf) headers.set("X-CSRF-Token", csrf);
  headers.set("X-Request-Id", crypto.randomUUID());
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const body = SAFE_METHODS.has(request.method) ? undefined : await request.arrayBuffer();
  const response = await fetch(target, { method: request.method, headers, body, cache: "no-store" });
  return new Response(response.body, { status: response.status, headers: { "Content-Type": response.headers.get("content-type") ?? "application/json", "X-Request-Id": response.headers.get("x-request-id") ?? "" } });
}
