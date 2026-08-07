import { TerminologyCreateForm } from "@/components/admin/forms";
import { getAdminIntegrator } from "@/lib/api";

interface Language { code: string; name: string; }
interface Term { id: string; source_language_code: string; target_language_code: string; source_term: string; target_term: string; notes: string | null; is_active: boolean; }

export default async function TerminologyPage() {
  const [languages, terms] = await Promise.all([getAdminIntegrator<Language[]>("/api/v1/ai/languages"), getAdminIntegrator<Term[]>("/api/v1/ai/terminology")]);
  return <><header className="admin-heading"><div><p className="kicker">Translation policy</p><h1>Terminology</h1></div><span>{terms.length} entries</span></header><div className="admin-two-column"><section className="admin-panel"><h2>Approved glossary</h2><div className="admin-list">{terms.map((term) => <article key={term.id}><div><strong>{term.source_term} → {term.target_term}</strong><p>{term.source_language_code.toUpperCase()} → {term.target_language_code.toUpperCase()}</p>{term.notes && <small>{term.notes}</small>}</div><span className={`status ${term.is_active ? "status-active" : "status-disabled"}`}>{term.is_active ? "active" : "disabled"}</span></article>)}</div></section><aside className="admin-panel"><h2>Add terminology</h2><TerminologyCreateForm languages={languages} /></aside></div></>;
}
