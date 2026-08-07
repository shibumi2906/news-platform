import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("accessibility source contracts", () => {
  it("provides named navigation and status/error announcements", () => {
    const root = resolve(import.meta.dirname, "..");
    const adminLayout = readFileSync(resolve(root, "app/admin/(protected)/layout.tsx"), "utf8");
    const forms = readFileSync(resolve(root, "components/admin/forms.tsx"), "utf8");
    const error = readFileSync(resolve(root, "app/admin/(protected)/error.tsx"), "utf8");
    expect(adminLayout).toContain('aria-label="Admin navigation"');
    expect(forms).toContain('role="status"');
    expect(error).toMatch(/role="alert"|aria-live/);
  });
});
