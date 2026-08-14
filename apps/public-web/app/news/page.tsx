import type { Metadata } from "next";
import Link from "next/link";
import { ArticleCard } from "@/components/article-card";
import { EmptyState } from "@/components/empty-state";
import { LanguageSwitcher } from "@/components/language-switcher";
import { getPublicArticles, getPublicCategories, getPublicLanguages } from "@/lib/api";

export const metadata: Metadata = { title: "News feed", description: "Latest published news." };

type SearchParams = {
  query?: string; lang?: string; category?: string; topic?: string;
  from_date?: string; to_date?: string; page?: string; sort?: "newest" | "oldest";
};

export default async function NewsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const page = Math.max(1, Number(params.page) || 1);
  const [articles, languages, categories] = await Promise.all([
    getPublicArticles({
      query: params.query, language: params.lang, category: params.category, topic: params.topic,
      from_date: params.from_date, to_date: params.to_date, page, sort: params.sort,
    }),
    getPublicLanguages(), getPublicCategories(),
  ]);
  const pageCount = Math.max(1, Math.ceil(articles.total / articles.page_size));
  const hrefFor = (nextPage: number) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) if (value && key !== "page") query.set(key, value);
    query.set("page", String(nextPage));
    return `/news?${query}`;
  };
  return (
    <section className="section-block">
      <div className="section-heading"><div><p className="kicker">Live desk</p><h1>News feed</h1></div><LanguageSwitcher languages={languages} /></div>
      <form className="filter-bar" action="/news">
        <label>Search <input name="query" type="search" defaultValue={params.query} placeholder="Search published reporting" /></label>
        <label>Category <select name="category" defaultValue={params.category ?? ""}><option value="">All categories</option>{categories.map((category) => <option key={category.slug} value={category.slug}>{category.slug}</option>)}</select></label>
        <label>Topic <input name="topic" defaultValue={params.topic} placeholder="Configured topic" /></label>
        <label>Language <select name="lang" defaultValue={params.lang ?? ""}><option value="">All languages</option>{languages.map((language) => <option key={language.code} value={language.code}>{language.code.toUpperCase()}</option>)}</select></label>
        <label>From <input name="from_date" type="date" defaultValue={params.from_date} /></label>
        <label>To <input name="to_date" type="date" defaultValue={params.to_date} /></label>
        <label>Sort <select name="sort" defaultValue={params.sort ?? "newest"}><option value="newest">Newest</option><option value="oldest">Oldest</option></select></label>
        <button type="submit">Apply filters</button>
      </form>
      {articles.items.length ? <div className="card-grid">{articles.items.map((article) => <ArticleCard key={article.id} article={article} language={params.lang} />)}</div> : <EmptyState title="No published articles" detail="Try another search or filter." />}
      {articles.total > articles.page_size && <nav className="pagination" aria-label="News pages">{page > 1 && <Link href={hrefFor(page - 1)}>Previous</Link>}<span>Page {page} of {pageCount}</span>{page < pageCount && <Link href={hrefFor(page + 1)}>Next</Link>}</nav>}
    </section>
  );
}
