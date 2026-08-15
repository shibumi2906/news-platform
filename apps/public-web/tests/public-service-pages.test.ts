import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import robots from "@/app/robots";
import { publicMetadata, publicRouteMetadata, publicServicePaths } from "@/lib/public-metadata";
import { serviceCopy } from "@/lib/service-content";

describe("public service pages and metadata", () => {
  it("provides canonical Open Graph metadata for public pages", () => {
    const metadata = publicMetadata("/about", "About", "About the newsroom");
    expect(metadata.alternates).toEqual({ canonical: "/about" });
    expect(metadata.openGraph).toMatchObject({ type: "website", url: "/about", title: "About" });
    expect(metadata.twitter).toMatchObject({ card: "summary", title: "About" });
  });

  it("ships the required service, error and discovery routes", () => {
    const root = resolve(import.meta.dirname, "..");
    for (const path of publicServicePaths) {
      expect(readFileSync(resolve(root, `app${path}/page.tsx`), "utf8")).toContain("ServicePage");
    }
    expect(readFileSync(resolve(root, "app/not-found.tsx"), "utf8")).toContain("Page not found");
    expect(readFileSync(resolve(root, "app/error.tsx"), "utf8")).toContain("500");
    expect(robots().rules).toEqual({ userAgent: "*", allow: "/", disallow: ["/admin/", "/api/"] });
  });

  it("sets canonical, hreflang and noindex without falsely localizing service copy", () => {
    const metadata = publicRouteMetadata("/news", "News", "Latest", { languages: ["en", "ar"], noindex: true });
    expect(metadata.alternates).toMatchObject({ canonical: "/news", languages: { en: "/news?lang=en", ar: "/news?lang=ar", "x-default": "/news" } });
    expect(metadata.robots).toEqual({ index: false, follow: true });
    expect(serviceCopy("privacy", "ar").direction).toBe("rtl");
    expect(serviceCopy("privacy", "fr").language).toBe("en");
  });
});
