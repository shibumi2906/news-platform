import { describe, expect, it } from "vitest";
import { formatMediaSize, safeStatusClass } from "@/lib/media";

describe("media administration presentation", () => {
  it("formats object sizes without exposing raw payloads", () => {
    expect(formatMediaSize(512)).toBe("512 B");
    expect(formatMediaSize(1500)).toBe("2 KB");
    expect(formatMediaSize(2 * 1024 * 1024)).toBe("2.0 MB");
  });

  it("does not interpolate untrusted status values into CSS classes", () => {
    expect(safeStatusClass("retry_wait")).toBe("status status-retry_wait");
    expect(safeStatusClass("failed onmouseover=alert(1)")).toBe("status");
  });
});
