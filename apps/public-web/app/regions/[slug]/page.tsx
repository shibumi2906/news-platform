import type { Metadata } from "next";
import { ArticleCard } from "@/components/article-card";
import { EmptyState } from "@/components/empty-state";
import { getPublicArticles, getPublicLanguages } from "@/lib/api";
import { publicRouteMetadata } from "@/lib/public-metadata";

type Props = { params: Promise<{ slug: string }>; searchParams: Promise<{ lang?: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const [{ slug }, languages] = await Promise.all([params, getPublicLanguages()]);
  return publicRouteMetadata(`/regions/${encodeURIComponent(slug)}`, slug, `Published reporting from the ${slug} region.`, { languages: languages.map((language) => language.code) });
}

export default async function RegionPage({ params, searchParams }: Props) {
  const [{ slug }, { lang }] = await Promise.all([params, searchParams]);
  const articles = await getPublicArticles({ language: lang, region: slug });
  return <section className="section-block"><p className="kicker">Region</p><h1>{slug}</h1>{articles.items.length ? <div className="card-grid">{articles.items.map((article) => <ArticleCard key={article.id} article={article} language={lang} />)}</div> : <EmptyState title="No published reporting" detail="This region does not have published articles yet." />}</section>;
}
