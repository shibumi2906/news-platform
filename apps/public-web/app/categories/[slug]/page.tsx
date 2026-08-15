import type { Metadata } from "next";
import { ArticleCard } from "@/components/article-card";
import { EmptyState } from "@/components/empty-state";
import { getPublicArticles } from "@/lib/api";
import { displayCategory } from "@/lib/presentation";
import { publicRouteMetadata } from "@/lib/public-metadata";
import { getPublicLanguages } from "@/lib/api";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const languages = await getPublicLanguages();
  return publicRouteMetadata(`/categories/${encodeURIComponent(slug)}`, displayCategory(slug), `Published reporting about ${displayCategory(slug)}.`, { languages: languages.map((language) => language.code) });
}

export default async function CategoryPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ lang?: string }> }) {
  const [{ slug }, { lang }] = await Promise.all([params, searchParams]);
  const articles = await getPublicArticles({ language: lang, category: slug });
  return <section className="section-block"><p className="kicker">Topic</p><h1>{displayCategory(slug)}</h1>{articles.items.length ? <div className="card-grid">{articles.items.map((article) => <ArticleCard key={article.id} article={article} language={lang} />)}</div> : <EmptyState title="No published reporting" detail="This topic does not have published articles yet." />}</section>;
}
