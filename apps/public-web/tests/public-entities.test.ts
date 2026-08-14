import { describe, expect, it } from "vitest";
import { publicEntitiesPath, publicEntityPath } from "@/lib/api";

describe("public entity API paths", () => {
  it("requests read-only entity listings and localized detail", () => {
    expect(publicEntitiesPath()).toBe("/api/v1/public/entities");
    expect(publicEntitiesPath("ar")).toBe("/api/v1/public/entities?language=ar");
    expect(publicEntityPath("entity/id", "ar")).toBe("/api/v1/public/entities/entity%2Fid?language=ar");
  });
});
