import type { Metadata } from "next";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { getPublicEntities, getPublicLanguages } from "@/lib/api";

export const metadata: Metadata = { title: "Entities", description: "People, places and organizations in published reporting." };

export default async function EntitiesPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  const { lang } = await searchParams;
  const [entities, languages] = await Promise.all([getPublicEntities(lang), getPublicLanguages()]);
  return <section className="section-block"><div className="section-heading"><div><p className="kicker">Connected reporting</p><h1>Entities</h1></div><nav className="language-links" aria-label="Entity language">{languages.map((language) => <Link key={language.code} aria-current={lang === language.code ? "page" : undefined} href={`/entities?lang=${language.code}`}>{language.code.toUpperCase()}</Link>)}</nav></div>{entities.length ? <div className="card-grid">{entities.map((entity) => <article className="article-card" key={entity.id}><p className="eyebrow">{entity.kind}</p><h2><Link href={`/entities/${entity.id}${lang ? `?lang=${encodeURIComponent(lang)}` : ""}`}>{entity.name}</Link></h2><small>{entity.article_count} published materials · <time dateTime={entity.latest_published_at}>{new Intl.DateTimeFormat(lang ?? "en", { dateStyle: "medium" }).format(new Date(entity.latest_published_at))}</time></small></article>)}</div> : <EmptyState title="No published entities" detail="Entities appear when linked reporting is published." />}</section>;
}
