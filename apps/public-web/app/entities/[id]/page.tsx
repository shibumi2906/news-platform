import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ArticleCard } from "@/components/article-card";
import { getPublicEntity } from "@/lib/api";
import { publicRouteMetadata, publicUrl } from "@/lib/public-metadata";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ lang?: string }> };

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  try { const entity = await getPublicEntity(id, lang); return publicRouteMetadata(`/entities/${entity.id}`, entity.name, `Published reporting about ${entity.name}`, { languages: entity.available_languages }); } catch { return {}; }
}

export default async function EntityPage({ params, searchParams }: Props) {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  try {
    const entity = await getPublicEntity(id, lang);
    const jsonLd = { "@context": "https://schema.org", "@type": "Thing", name: entity.name, additionalType: entity.kind, url: `${publicUrl}/entities/${entity.id}` };
    return <section className="section-block"><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replaceAll("<", "\\u003c") }} /><p className="kicker">{entity.kind}</p><h1>{entity.name}</h1><ol className="timeline">{entity.articles.map((article) => <li key={article.id}><time dateTime={article.published_at}>{new Intl.DateTimeFormat(article.language, { dateStyle: "medium", timeStyle: "short" }).format(new Date(article.published_at))}</time><ArticleCard article={article} language={lang} /></li>)}</ol></section>;
  } catch (error) {
    if (error instanceof Response && error.status === 404) notFound();
    throw error;
  }
}
