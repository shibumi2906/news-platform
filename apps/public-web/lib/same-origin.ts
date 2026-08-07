export function isSameOrigin(request: Request, publicUrl = process.env.NEXT_PUBLIC_WEB_URL): boolean {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite === "cross-site") return false;
  const origin = request.headers.get("origin");
  const expected = new URL(publicUrl ?? request.url).origin;
  if (origin !== null) return origin === expected;
  return fetchSite === "same-origin";
}

export function isSafeBackendPath(path: string[]): boolean {
  return path.length > 0 && path.every(
    (segment) => segment !== "." && segment !== ".." && /^[A-Za-z0-9._~-]+$/.test(segment),
  );
}
