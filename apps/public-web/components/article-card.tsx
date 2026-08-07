import Link from "next/link";
import type { PublicArticle } from "@/lib/types";
import { directionFor, displayCategory } from "@/lib/presentation";

export function ArticleCard({ article, language }: { article: PublicArticle; language?: string }) {
  const href = `/articles/${article.id}${language ? `?lang=${encodeURIComponent(language)}` : ""}`;
  return (
    <article className="article-card" dir={directionFor(article.direction)}>
      <div className="eyebrow">
        {article.taxonomy.slice(0, 2).map((category) => (
          <Link key={category} href={`/categories/${category}`}>
            {displayCategory(category)}
          </Link>
        ))}
      </div>
      <h2><Link href={href}>{article.title}</Link></h2>
      <p>{article.summary || article.lead || "Open the article for the full report."}</p>
      <footer>
        <time dateTime={article.published_at}>
          {new Intl.DateTimeFormat(article.language, { dateStyle: "medium" }).format(
            new Date(article.published_at),
          )}
        </time>
        <span>{article.language.toUpperCase()}</span>
      </footer>
    </article>
  );
}
