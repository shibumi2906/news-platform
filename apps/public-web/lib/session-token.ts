import { createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "news_admin_session";

interface SessionPayload {
  actor: string;
  expiresAt: number;
}

const encode = (value: string): string => Buffer.from(value).toString("base64url");
const decode = (value: string): string => Buffer.from(value, "base64url").toString();

export function createSessionToken(actor: string, secret: string, now = Date.now()): string {
  const payload = encode(JSON.stringify({ actor, expiresAt: now + 8 * 60 * 60 * 1000 }));
  return `${payload}.${sign(payload, secret)}`;
}

export function verifySessionToken(
  token: string | undefined,
  secret: string,
  now = Date.now(),
): SessionPayload | null {
  if (!token) return null;
  const [payload, signature, extra] = token.split(".");
  if (!payload || !signature || extra) return null;
  const expected = sign(payload, secret);
  const suppliedBuffer = Buffer.from(signature);
  const expectedBuffer = Buffer.from(expected);
  if (
    suppliedBuffer.length !== expectedBuffer.length ||
    !timingSafeEqual(suppliedBuffer, expectedBuffer)
  ) return null;
  try {
    const parsed = JSON.parse(decode(payload)) as SessionPayload;
    return parsed.expiresAt > now && parsed.actor ? parsed : null;
  } catch {
    return null;
  }
}

function sign(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}
