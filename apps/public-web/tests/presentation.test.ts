import { describe, expect, it } from "vitest";
import { articleDescription, directionFor, displayCategory } from "@/lib/presentation";
import type { PublicArticle } from "@/lib/types";

const article: PublicArticle = {
  id: "1", article_version_id: "2", title: "Headline", lead: "Lead", body: "Body",
  summary: "Summary", tags: [], taxonomy: [], regions: [], language: "en", direction: "ltr",
  available_languages: ["en"], published_at: "2026-08-07T00:00:00Z",
  updated_at: "2026-08-07T00:00:00Z", facts: [], entities: [], sources: [],
};

describe("public presentation helpers", () => {
  it("normalizes directions and category names", () => {
    expect(directionFor("rtl")).toBe("rtl");
    expect(directionFor("unexpected")).toBe("ltr");
    expect(displayCategory("space-launches")).toBe("Space Launches");
  });

  it("uses a stable SEO description fallback order", () => {
    expect(articleDescription(article)).toBe("Summary");
    expect(articleDescription({ ...article, summary: null })).toBe("Lead");
    expect(articleDescription({ ...article, summary: null, lead: null })).toBe("Body");
  });
});
