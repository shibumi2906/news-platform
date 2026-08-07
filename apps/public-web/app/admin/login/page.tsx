import type { Metadata } from "next";

export const metadata: Metadata = { title: "Admin sign in", robots: { index: false, follow: false } };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  return <section className="login-shell"><form className="admin-form login-card" action="/api/session" method="post"><p className="kicker">Protected workspace</p><h1>Newsroom sign in</h1>{error && <p className="form-error" role="alert">The credentials were not accepted.</p>}<label>Username<input name="username" autoComplete="username" required /></label><label>Password<input name="password" type="password" autoComplete="current-password" required /></label><button type="submit">Start secure session</button></form></section>;
}
