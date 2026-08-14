import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ArticleCard } from "@/components/article-card";
import { getPublicEntity } from "@/lib/api";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ lang?: string }> };

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  try { const entity = await getPublicEntity(id, lang); return { title: entity.name, description: `Published reporting about ${entity.name}` }; } catch { return {}; }
}

export default async function EntityPage({ params, searchParams }: Props) {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  try {
    const entity = await getPublicEntity(id, lang);
    return <section className="section-block"><p className="kicker">{entity.kind}</p><h1>{entity.name}</h1><ol className="timeline">{entity.articles.map((article) => <li key={article.id}><time dateTime={article.published_at}>{new Intl.DateTimeFormat(article.language, { dateStyle: "medium", timeStyle: "short" }).format(new Date(article.published_at))}</time><ArticleCard article={article} language={lang} /></li>)}</ol></section>;
  } catch (error) {
    if (error instanceof Response && error.status === 404) notFound();
    throw error;
  }
}
