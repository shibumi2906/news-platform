import { getAdminSite } from "@/lib/api";

interface Status { status: string; components: Record<string, string>; jobs: { processing: number; dlq: number }; version: string }
interface Alert { code: string; severity: string; value: string }

export default async function SystemPage() {
  const [status, alerts] = await Promise.all([
    getAdminSite<Status>("/api/v1/admin/system/status"),
    getAdminSite<Alert[]>("/api/v1/admin/system/alerts"),
  ]);
  return <><header className="admin-heading"><div><p className="kicker">Operations</p><h1>System health</h1></div><span>{status.status} · v{status.version}</span></header><div className="metric-grid">{Object.entries(status.components).map(([name, value]) => <article key={name}><span>{name.replace("_", " ")}</span><strong>{value}</strong></article>)}<article><span>Processing jobs</span><strong>{status.jobs.processing}</strong></article><article><span>DLQ</span><strong>{status.jobs.dlq}</strong></article></div><section className="admin-panel"><h2>Active alerts</h2>{alerts.length ? alerts.map((alert) => <p role="alert" key={alert.code}>{alert.severity}: {alert.code} ({alert.value})</p>) : <p>No active alert conditions.</p>}</section></>;
}
