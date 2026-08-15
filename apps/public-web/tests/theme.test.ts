import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  defaultPublicTheme,
  publicThemeAttributes,
  publicThemes,
  resolvePublicTheme,
} from "@/lib/theme";

describe("public design themes", () => {
  it("selects each configured theme and falls back safely", () => {
    expect(publicThemes).toEqual(["editorial", "midnight", "signal"]);
    expect(resolvePublicTheme("midnight")).toBe("midnight");
    expect(resolvePublicTheme(" SIGNAL ")).toBe("signal");
    expect(resolvePublicTheme("unknown-theme")).toBe(defaultPublicTheme);
    expect(resolvePublicTheme("")).toBe(defaultPublicTheme);
  });

  it("renders shared page chrome with attributes for more than one theme", () => {
    expect(publicThemeAttributes("editorial")).toEqual({ "data-theme": "editorial" });
    expect(publicThemeAttributes("midnight")).toEqual({ "data-theme": "midnight" });
    const root = resolve(import.meta.dirname, "..");
    const layout = readFileSync(resolve(root, "app/layout.tsx"), "utf8");
    const home = readFileSync(resolve(root, "app/page.tsx"), "utf8");
    const css = readFileSync(resolve(root, "app/globals.css"), "utf8");
    expect(layout).toContain("publicThemeAttributes()");
    expect(home).toContain('className="hero"');
    expect(css).toContain('html[data-theme="midnight"]');
    expect(css).toContain('html[data-theme="signal"]');
  });
});
