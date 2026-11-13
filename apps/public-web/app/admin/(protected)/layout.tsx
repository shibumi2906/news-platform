import { AdminNavigation } from "@/components/admin/navigation";
import { requireSession } from "@/lib/session";

const links = [
  ["Overview", "/admin", null], ["Selected materials", "/admin/materials", "system:read"], ["Sources", "/admin/sources", "sources:manage"],
  ["Topics", "/admin/topics", "topics:manage"],
  ["Languages", "/admin/languages", "topics:manage"],
  ["Glossary", "/admin/terminology", "topics:manage"],
  ["Incoming", "/admin/incoming", "articles:read"],
  ["Articles", "/admin/articles", "articles:read"], ["Media", "/admin/media", "media:manage"],
  ["Distribution", "/admin/distribution", "distribution:manage"],
  ["Billing", "/admin/billing", "billing:manage"], ["Advertising", "/admin/advertising", "advertising:manage"],
  ["AI settings", "/admin/ai", "topics:manage"], ["AI telemetry", "/admin/telemetry", "system:read"],
  ["Users & roles", "/admin/security", "users:read"], ["Audit log", "/admin/audit", "audit:read"],
  ["Jobs & DLQ", "/admin/jobs", "jobs:manage"], ["System health", "/admin/system", "system:read"],
] as const;

export const dynamic = "force-dynamic";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();
  const visibleLinks = links.filter(([, , permission]) => permission === null || session.permissions.includes(permission));
  return <div className="admin-shell"><aside className="admin-sidebar"><div><p className="kicker">Newsroom OS</p><h2>Control room</h2><p className="admin-actor">Signed in as {session.actor}</p></div><AdminNavigation links={visibleLinks} aria-label="Admin navigation" /><form action="/api/session" method="post"><input type="hidden" name="action" value="logout" /><button type="submit" className="quiet-button">Sign out</button></form></aside><section className="admin-content">{children}</section></div>;
}
