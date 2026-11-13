import Link from "next/link";
import { getAdminIntegrator } from "@/lib/api";
import { requireSession } from "@/lib/session";

export default async function AdminOverview() {
  const session = await requireSession();
  if (!session.permissions.includes("system:read")) {
    return <header className="admin-heading"><h1>Overview</h1></header>;
  }
  const overview = await getAdminIntegrator<{ selected: number; source_errors: number; processing_errors: number }>("/api/v1/admin/selection-overview");
  return <>
    <header className="admin-heading"><h1>Overview</h1></header>
    <div className="metric-grid">
      <article><Link href="/admin/materials">Selected in the last 24 hours</Link><strong>{overview.selected}</strong></article>
      <article>{session.permissions.includes("sources:manage") ? <Link href="/admin/sources">Sources with errors</Link> : <span>Sources with errors</span>}<strong>{overview.source_errors}</strong></article>
      <article><Link href="/admin/materials?view=history&errors_only=true">Processing errors</Link><strong>{overview.processing_errors}</strong></article>
    </div>
  </>;
}
