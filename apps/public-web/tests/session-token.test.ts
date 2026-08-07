import { describe, expect, it } from "vitest";
import { createSessionToken, verifySessionToken } from "@/lib/session-token";

describe("admin session token", () => {
  it("round-trips an actor without exposing the secret", () => {
    const token = createSessionToken("editor", "strong-test-secret", 1_000);
    expect(token).not.toContain("strong-test-secret");
    expect(verifySessionToken(token, "strong-test-secret", 2_000)).toEqual({
      actor: "editor",
      expiresAt: 28_801_000,
    });
  });

  it("rejects tampering, the wrong secret and expiry", () => {
    const token = createSessionToken("editor", "strong-test-secret", 1_000);
    expect(verifySessionToken(`${token}x`, "strong-test-secret", 2_000)).toBeNull();
    expect(verifySessionToken(token, "different-secret", 2_000)).toBeNull();
    expect(verifySessionToken(token, "strong-test-secret", 28_801_001)).toBeNull();
  });
});
