import { LanguageToggle } from "@/components/admin/forms";
import { getAdminIntegrator } from "@/lib/api";

interface Language { id: string; code: string; name: string; direction: string; priority: number; is_active: boolean; translation_enabled: boolean; }

export default async function LanguagesPage() {
  const languages = await getAdminIntegrator<Language[]>("/api/v1/ai/languages");
  return <><header className="admin-heading"><div><p className="kicker">Multilingual</p><h1>Languages</h1></div><span>{languages.length} configured</span></header><section className="admin-panel"><div className="language-admin-grid">{languages.map((language) => <article key={language.id} dir={language.direction}><div><strong>{language.name}</strong><p>{language.code} · {language.direction.toUpperCase()}</p></div><span className={`status ${language.translation_enabled ? "status-active" : "status-disabled"}`}>{language.translation_enabled ? "translation on" : "translation off"}</span><LanguageToggle language={language} /></article>)}</div></section></>;
}
