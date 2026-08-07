import { describe, expect, it } from "vitest";
import { isSameOrigin } from "@/lib/same-origin";

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
});
