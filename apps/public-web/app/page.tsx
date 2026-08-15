import Link from "next/link";
import { ArticleCard } from "@/components/article-card";
import { EmptyState } from "@/components/empty-state";
import { getPublicArticles, getPublicCategories } from "@/lib/api";
import { displayCategory } from "@/lib/presentation";
import { publicMetadata } from "@/lib/public-metadata";

export const metadata = publicMetadata("/", "Signal Desk", "Independent, source-aware reporting from the News Platform.");

export default async function HomePage() {
  const [articles, categories] = await Promise.all([getPublicArticles(), getPublicCategories()]);
  const [lead, ...rest] = articles.items;
  return (
    <>
      <section className="hero">
        <p className="kicker">Newsroom intelligence, editorially controlled</p>
        <h1>The day’s signal, without the noise.</h1>
        <p>Verified drafts, transparent sources and human publication decisions.</p>
      </section>
      {lead ? (
        <section className="lead-grid" aria-label="Top story">
          <article className="lead-story" dir={lead.direction}>
            <span className="kicker">Top story · {lead.language.toUpperCase()}</span>
            <h2><Link href={`/articles/${lead.id}`}>{lead.title}</Link></h2>
            <p>{lead.lead || lead.summary}</p>
          </article>
          <aside className="topic-rail" aria-label="Trending topics">
            <h2>Explore topics</h2>
            {categories.slice(0, 6).map((category) => (
              <Link key={category.slug} href={`/categories/${category.slug}`}>
                <span>{displayCategory(category.slug)}</span>
                <strong>{category.article_count}</strong>
              </Link>
            ))}
          </aside>
        </section>
      ) : (
        <EmptyState title="The desk is quiet" detail="Published reporting will appear here." />
      )}
      {rest.length > 0 && (
        <section className="section-block">
          <div className="section-heading"><h2>Latest</h2><Link href="/news">Full feed →</Link></div>
          <div className="card-grid">{rest.slice(0, 6).map((article) => <ArticleCard key={article.id} article={article} />)}</div>
        </section>
      )}
    </>
  );
}
