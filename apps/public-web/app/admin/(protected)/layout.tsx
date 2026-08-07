import Link from "next/link";
import { requireSession } from "@/lib/session";

const links = [
  ["Overview", "/admin"], ["Sources", "/admin/sources"], ["Topics", "/admin/topics"],
  ["Languages", "/admin/languages"], ["Glossary", "/admin/terminology"],
  ["Incoming", "/admin/incoming"], ["Articles", "/admin/articles"], ["Media", "/admin/media"],
  ["Distribution", "/admin/distribution"], ["AI telemetry", "/admin/telemetry"],
];

export const dynamic = "force-dynamic";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();
  return <div className="admin-shell"><aside className="admin-sidebar"><div><p className="kicker">Newsroom OS</p><h2>Control room</h2><p className="admin-actor">Signed in as {session.actor}</p></div><nav aria-label="Admin navigation">{links.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}</nav><form action="/api/session" method="post"><input type="hidden" name="action" value="logout" /><button type="submit" className="quiet-button">Sign out</button></form></aside><section className="admin-content">{children}</section></div>;
}
