import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/session-token";

export async function requireSession(): Promise<{ actor: string }> {
  const secret = process.env.SESSION_SECRET;
  if (!secret) throw new Error("SESSION_SECRET is required");
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = verifySessionToken(token, secret);
  if (!session) redirect("/admin/login");
  return { actor: session.actor };
}
