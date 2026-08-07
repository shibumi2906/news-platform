import { CreateArticleButton } from "@/components/admin/forms";
import { getAdminSite } from "@/lib/api";

interface Incoming { id: string; version_id: string; package_id: string; latest_version: number; title: string; language: string; received_at: string; }

export default async function IncomingPage() {
  const packages = await getAdminSite<Incoming[]>("/api/v1/admin/incoming-packages");
  return <><header className="admin-heading"><div><p className="kicker">Site inbox</p><h1>Incoming packages</h1></div><span>{packages.length} latest packages</span></header><section className="admin-panel"><div className="admin-list">{packages.map((item) => <article key={item.id}><div><strong>{item.title}</strong><p>{item.language.toUpperCase()} · package v{item.latest_version}</p><small>{new Date(item.received_at).toLocaleString()}</small></div><CreateArticleButton packageVersionId={item.version_id} /></article>)}</div>{packages.length === 0 && <p>No incoming packages.</p>}</section></>;
}
