import { getAdminSite } from "@/lib/api";

interface Audit { id: string; actor: string; action: string; resource_type: string; outcome: string; correlation_id?: string; created_at: string }

export default async function AuditPage() {
  const rows = await getAdminSite<Audit[]>("/api/v1/admin/security/audit");
  return <><header className="admin-heading"><div><p className="kicker">Immutable activity trail</p><h1>Audit log</h1></div></header><section className="admin-panel"><div className="table-wrap"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Outcome</th><th>Correlation ID</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{new Date(row.created_at).toLocaleString()}</td><td>{row.actor}</td><td>{row.action}<br /><small>{row.resource_type}</small></td><td>{row.outcome}</td><td><code>{row.correlation_id ?? "—"}</code></td></tr>)}</tbody></table></div></section></>;
}
