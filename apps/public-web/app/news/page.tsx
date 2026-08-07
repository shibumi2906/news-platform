import type { Metadata } from "next";
import { ArticleCard } from "@/components/article-card";
import { EmptyState } from "@/components/empty-state";
import { LanguageSwitcher } from "@/components/language-switcher";
import { getPublicArticles, getPublicLanguages } from "@/lib/api";

export const metadata: Metadata = { title: "News feed", description: "Latest published news." };

export default async function NewsPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  const { lang } = await searchParams;
  const [articles, languages] = await Promise.all([getPublicArticles(lang), getPublicLanguages()]);
  return (
    <section className="section-block">
      <div className="section-heading"><div><p className="kicker">Live desk</p><h1>News feed</h1></div><LanguageSwitcher languages={languages} /></div>
      {articles.length ? <div className="card-grid">{articles.map((article) => <ArticleCard key={article.id} article={article} language={lang} />)}</div> : <EmptyState title="No published articles" detail="Try the original language or return later." />}
    </section>
  );
}
