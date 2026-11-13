import Link from "next/link";
import { SiteDeliveryMode } from "@/components/admin/site-delivery";
import { requireSession } from "@/lib/session";
import { getAdminIntegrator } from "@/lib/api";

interface SourceRef { url: string; source_id: string; source_name?: string; published_at: string }
interface Selected {
  id: string;
  content: { title?: string; summary?: string; lead?: string; body?: string };
  created_at: string;
  topics: Array<{ id: string; slug: string; label?: string }>;
  taxonomy: string[];
  categories: Array<{ slug: string; topic_id: string; label?: string }>;
  sources: SourceRef[];
  reasons: Array<{ topic: string; reason: Record<string, unknown> }>;
}
interface History {
  id: string;
  title: string;
  url: string;
  source: string;
  status: string;
  error: string | null;
  decisions: Array<{ topic: string; passed: boolean; reason: Record<string, unknown> }>;
}
interface Page<T> { items: T[]; has_more: boolean }

function reasonText(reason: Record<string, unknown>) {
  return Object.values(reason).flat().filter((item) => typeof item === "string").join(" · ");
}

function original(url: string) {
  return /^https?:\/\//i.test(url) ? url : undefined;
}

export default async function MaterialsPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [search, session] = await Promise.all([searchParams, requireSession()]);
  const params = new URLSearchParams();
  for (const key of ["topic", "source", "since", "until"]) {
    const value = search[key];
    if (typeof value === "string" && value) params.set(key, value);
  }
  const number = Number(search.page);
  const page = Number.isInteger(number) && number > 0 && number <= 10000 ? number : 1;
  const view = search.view === "history" || search.view === "sites" ? search.view : "selected";
  const base = "/admin/materials";
  const errorsOnly = search.errors_only === "true";
  const filtered = (next: number) => {
    const query = new URLSearchParams(view === "selected" ? params : undefined);
    query.set("view", view);
    if (view === "history" && errorsOnly) query.set("errors_only", "true");
    query.set("page", String(next));
    return `${base}?${query}`;
  };
  params.set("page", String(page));
  const [selection, history, sites, filters] = await Promise.all([
    view === "selected" ? getAdminIntegrator<Page<Selected>>(`/api/v1/admin/selected-materials?${params}`) : null,
    view === "history" ? getAdminIntegrator<Page<History>>(`/api/v1/admin/selection-history?page=${page}&errors_only=${errorsOnly}`) : null,
    view === "sites" ? getAdminIntegrator<Array<{ id: string; name: string; active: boolean; delivery_mode: string; last_pull_at: string | null }>>("/api/v1/admin/site-feed-activity") : null,
    view === "selected" ? getAdminIntegrator<{ topics: Array<{slug: string; name: string}>; sources: Array<{id: string; name: string}> }>("/api/v1/admin/selection-filters") : null,
  ]);
  return <>
    <header className="admin-heading"><h1>Selected materials</h1></header>
    <nav className="quick-links" aria-label="Material views">
      <Link href={base} aria-current={view === "selected" ? "page" : undefined}>Selected</Link>
      <Link href={`${base}?view=history`} aria-current={view === "history" ? "page" : undefined}>Selection history</Link>
      <Link href={`${base}?view=sites`} aria-current={view === "sites" ? "page" : undefined}>Connected sites</Link>
    </nav>
    {selection && <section className="admin-panel">
      <form className="material-filters" action={base}>
        <label>Topic<select name="topic" defaultValue={params.get("topic") ?? ""}>
          <option value="">All topics</option>
          {filters?.topics.map((topic) => <option key={topic.slug} value={topic.slug}>{topic.name}</option>)}
        </select></label>
        <label>Source<select name="source" defaultValue={params.get("source") ?? ""}>
          <option value="">All sources</option>
          {filters?.sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
        </select></label>
        <label>Selected from<input type="date" name="since" defaultValue={params.get("since") ?? ""} /></label>
        <label>Selected through<input type="date" name="until" defaultValue={params.get("until") ?? ""} /></label>
        <button type="submit">Apply filters</button>
      </form>
      {!selection.items.length && <p>No matching materials. Check Selection history for rejected items and processing errors.</p>}
      {selection.items.map((item) => <details className="material-card" key={item.id}>
        <summary><strong>{item.content.title ?? "Untitled material"}</strong>
          <span>{item.sources[0]?.source_name ?? "Source"} · {new Date(item.sources[0]?.published_at ?? item.created_at).toLocaleDateString()}</span>
        </summary>
        <p>{item.content.summary || item.content.lead}</p>
        <div className="chip-row">
          {item.topics.length ? item.topics.map((topic) => <span key={topic.id}>{topic.label ?? topic.slug}</span>) : item.taxonomy.map((label) => <span key={label}>{label}</span>)}
          {item.categories.map((category) => <span key={`${category.topic_id}:${category.slug}`}>{category.label ?? category.slug}</span>)}
        </div>
        {item.reasons.map((reason, index) => <p key={index}><strong>{reason.topic}</strong> · {reasonText(reason.reason)}</p>)}
        {item.content.body && <p className="material-body">{item.content.body}</p>}
        <ul>{item.sources.filter((source) => original(source.url)).map((source, index) => <li key={index}>
          <a href={original(source.url)} target="_blank" rel="noreferrer">{source.source_name ?? "Open original"}</a>
        </li>)}</ul>
      </details>)}
    </section>}
    {history && <section className="admin-panel">
      <Link href={errorsOnly ? `${base}?view=history` : `${base}?view=history&errors_only=true`}>{errorsOnly ? "Show all decisions" : "Show processing errors"}</Link>
      {!history.items.length && <p>{errorsOnly ? "No processing errors." : "No source materials collected yet."}</p>}
      {history.items.map((item) => <details className="material-card" key={item.id}>
        <summary><strong>{item.title}</strong><span>{item.source} · {
          item.status === "failed" ? "Processing error" : item.status !== "processed" ? "Awaiting processing" :
          item.decisions.some((decision) => decision.passed) ? "Selected" : "Rejected"
        }</span></summary>
        {item.error && <p className="form-error">{item.error}</p>}
        {item.decisions.map((decision, index) => <p key={index}>{decision.topic} · {decision.passed ? "Matched" : "Rejected"} · {reasonText(decision.reason)}</p>)}
        {original(item.url) && <a href={original(item.url)} target="_blank" rel="noreferrer">Open original</a>}
      </details>)}
    </section>}
    {sites && <section className="admin-panel admin-list">
      {!sites.length && <p>No sites connected.</p>}
      {sites.map((site) => <article key={site.id}>
        <div><strong>{site.name}</strong><p>{site.active ? "Active" : "Paused"} · {site.delivery_mode === "pull" ? "Site requests materials" : "Send to site"}</p><small>Connection ID: {site.id}</small></div>
        {session.permissions.includes("jobs:manage") && <SiteDeliveryMode id={site.id} mode={site.delivery_mode} />}
        <span>Last successful request: {site.last_pull_at ? new Date(site.last_pull_at).toLocaleString() : "None yet"}</span>
      </article>)}
    </section>}
    {(selection || history) && <nav className="quick-links" aria-label="Pagination">
      {page > 1 && <Link href={filtered(page - 1)}>Previous</Link>}
      {(selection?.has_more || history?.has_more) && <Link href={filtered(page + 1)}>Next</Link>}
    </nav>}
  </>;
}
