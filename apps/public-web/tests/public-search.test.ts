import { describe, expect, it } from "vitest";
import { publicArticlePath } from "@/lib/api";

describe("public article search request", () => {
  it("serializes search, configured taxonomy filters, dates and pagination", () => {
    expect(publicArticlePath({
      query: "launch update", category: "launches", topic: "space", language: "en",
      from_date: "2026-08-01", to_date: "2026-08-31", page: 2, page_size: 10, sort: "oldest",
    })).toBe("/api/v1/public/articles?query=launch+update&category=launches&topic=space&language=en&from_date=2026-08-01&to_date=2026-08-31&page=2&page_size=10&sort=oldest");
  });

  it("keeps the default public listing read-only and unfiltered", () => {
    expect(publicArticlePath()).toBe("/api/v1/public/articles");
  });
});
