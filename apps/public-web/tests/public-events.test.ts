import { describe, expect, it } from "vitest";
import { publicEventPath, publicEventsPath } from "@/lib/api";

describe("public event API paths", () => {
  it("requests read-only event listings and localized timeline detail", () => {
    expect(publicEventsPath()).toBe("/api/v1/public/events");
    expect(publicEventsPath("ar")).toBe("/api/v1/public/events?language=ar");
    expect(publicEventPath("event/id", "ar")).toBe("/api/v1/public/events/event%2Fid?language=ar");
  });
});
