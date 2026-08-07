import { describe, expect, it } from "vitest";
import { isSafeBackendPath, isSameOrigin } from "@/lib/same-origin";

describe("same-origin protection", () => {
  it("uses the configured public origin behind a reverse proxy", () => {
    const request = new Request("http://public-web:3000/api/session", {
      headers: { origin: "https://news.example" },
    });
    expect(isSameOrigin(request, "https://news.example")).toBe(true);
    expect(isSameOrigin(request, "https://other.example")).toBe(false);
  });

  it("always rejects explicit cross-site browser requests", () => {
    const request = new Request("https://news.example/api/session", {
      headers: { origin: "https://news.example", "sec-fetch-site": "cross-site" },
    });
    expect(isSameOrigin(request, "https://news.example")).toBe(false);
  });

  it("fails closed without browser origin metadata", () => {
    const untrusted = new Request("https://news.example/api/session");
    const sameOrigin = new Request("https://news.example/api/session", {
      headers: { "sec-fetch-site": "same-origin" },
    });
    expect(isSameOrigin(untrusted, "https://news.example")).toBe(false);
    expect(isSameOrigin(sameOrigin, "https://news.example")).toBe(true);
  });

  it("rejects traversal and malformed backend paths", () => {
    expect(isSafeBackendPath(["api", "v1", "admin", "articles"])).toBe(true);
    expect(isSafeBackendPath(["api", "..", "health"])).toBe(false);
    expect(isSafeBackendPath([])).toBe(false);
    expect(isSafeBackendPath(["api", "path%2fescape"])).toBe(false);
  });
});
