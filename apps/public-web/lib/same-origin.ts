export function isSameOrigin(request: Request, publicUrl = process.env.NEXT_PUBLIC_WEB_URL): boolean {
  if (request.headers.get("sec-fetch-site") === "cross-site") return false;
  const origin = request.headers.get("origin");
  const expected = new URL(publicUrl ?? request.url).origin;
  return origin === null || origin === expected;
}
