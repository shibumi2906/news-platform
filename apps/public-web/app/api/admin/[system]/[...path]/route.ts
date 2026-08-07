import { cookies } from "next/headers";
import { backendUrl } from "@/lib/api";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/session-token";

type Context = { params: Promise<{ system: string; path: string[] }> };

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;

async function proxy(request: Request, context: Context): Promise<Response> {
  if (request.headers.get("sec-fetch-site") === "cross-site") {
    return Response.json({ error: "cross-site request rejected" }, { status: 403 });
  }
  const secret = process.env.SESSION_SECRET;
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = secret ? verifySessionToken(token, secret) : null;
  if (!session) return Response.json({ error: "authentication required" }, { status: 401 });
  const { system, path } = await context.params;
  if (system !== "site" && system !== "integrator") {
    return Response.json({ error: "unknown backend" }, { status: 404 });
  }
  if (path.some((segment) => !/^[A-Za-z0-9._~-]+$/.test(segment))) {
    return Response.json({ error: "invalid backend path" }, { status: 400 });
  }
  const adminToken = process.env.ADMIN_API_TOKEN;
  if (!adminToken) return Response.json({ error: "admin backend is not configured" }, { status: 503 });
  const sourceUrl = new URL(request.url);
  const target = `${backendUrl(system)}/${path.join("/")}${sourceUrl.search}`;
  const headers = new Headers({ "X-Admin-Token": adminToken, "X-Actor-Id": session.actor });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
  const response = await fetch(target, { method: request.method, headers, body, cache: "no-store" });
  return new Response(response.body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") ?? "application/json",
      "X-Request-Id": response.headers.get("x-request-id") ?? "",
    },
  });
}
