import type { Metadata } from "next";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { getPublicEvents, getPublicLanguages } from "@/lib/api";

export const metadata: Metadata = { title: "Events", description: "Published reporting grouped by event." };

export default async function EventsPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  const { lang } = await searchParams;
  const [events, languages] = await Promise.all([getPublicEvents(lang), getPublicLanguages()]);
  return <section className="section-block"><div className="section-heading"><div><p className="kicker">Connected reporting</p><h1>Events</h1></div><nav className="language-links" aria-label="Event language">{languages.map((language) => <Link key={language.code} aria-current={lang === language.code ? "page" : undefined} href={`/events?lang=${language.code}`}>{language.code.toUpperCase()}</Link>)}</nav></div>{events.length ? <div className="card-grid">{events.map((event) => <article className="article-card" key={event.id}><p className="eyebrow">{event.taxonomy.join(" · ")}</p><h2><Link href={`/events/${event.id}${lang ? `?lang=${encodeURIComponent(lang)}` : ""}`}>{event.title}</Link></h2>{event.summary && <p>{event.summary}</p>}<small>{event.article_count} published materials · <time dateTime={event.latest_published_at}>{new Intl.DateTimeFormat(lang ?? "en", { dateStyle: "medium" }).format(new Date(event.latest_published_at))}</time></small></article>)}</div> : <EmptyState title="No published events" detail="Events appear when related reporting is published." />}</section>;
}
