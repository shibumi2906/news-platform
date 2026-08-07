import { SourceCreateForm, SourceStateButton } from "@/components/admin/forms";
import { getAdminIntegrator } from "@/lib/api";

interface Source { id: string; name: string; feed_url: string; adapter_type: string; poll_interval_seconds: number; is_active: boolean; status: string; }

export default async function SourcesPage() {
  const sources = await getAdminIntegrator<Source[]>("/api/v1/sources");
  return <><header className="admin-heading"><div><p className="kicker">Integrator</p><h1>Sources</h1></div><span>{sources.length} configured</span></header><div className="admin-two-column"><section className="admin-panel"><h2>Configured sources</h2>{sources.length ? <div className="admin-list">{sources.map((source) => <article key={source.id}><div><strong>{source.name}</strong><p>{source.adapter_type.toUpperCase()} · every {source.poll_interval_seconds}s</p><small>{source.feed_url}</small></div><div className="row-actions"><span className={`status status-${source.status}`}>{source.status}</span><SourceStateButton id={source.id} active={source.is_active} /></div></article>)}</div> : <p>No sources configured.</p>}</section><aside className="admin-panel"><h2>Add source</h2><SourceCreateForm /></aside></div></>;
}
