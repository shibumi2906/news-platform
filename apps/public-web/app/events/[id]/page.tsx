import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ArticleCard } from "@/components/article-card";
import { getPublicEvent } from "@/lib/api";
import { publicRouteMetadata, publicUrl } from "@/lib/public-metadata";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ lang?: string }> };

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  try {
    const event = await getPublicEvent(id, lang);
    return publicRouteMetadata(`/events/${event.id}`, event.title, event.summary ?? `Timeline for ${event.title}`, { languages: event.available_languages });
  } catch { return {}; }
}

export default async function EventPage({ params, searchParams }: Props) {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  try {
    const event = await getPublicEvent(id, lang);
    const jsonLd = { "@context": "https://schema.org", "@type": "Event", name: event.title, description: event.summary ?? undefined, url: `${publicUrl}/events/${event.id}`, subEvent: event.articles.map((article) => ({ "@type": "NewsArticle", headline: article.title, datePublished: article.published_at, url: `${publicUrl}/articles/${article.id}` })) };
    return <section className="section-block"><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replaceAll("<", "\\u003c") }} /><p className="kicker">Event timeline</p><h1>{event.title}</h1>{event.summary && <p className="article-lead">{event.summary}</p>}<ol className="timeline">{event.articles.map((article) => <li key={article.id}><time dateTime={article.published_at}>{new Intl.DateTimeFormat(article.language, { dateStyle: "medium", timeStyle: "short" }).format(new Date(article.published_at))}</time><ArticleCard article={article} language={lang} /></li>)}</ol></section>;
  } catch (error) {
    if (error instanceof Response && error.status === 404) notFound();
    throw error;
  }
}
