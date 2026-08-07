import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getPublicArticle, getPublicLanguages } from "@/lib/api";
import { articleDescription, directionFor, displayCategory } from "@/lib/presentation";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ lang?: string }> };

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  try {
    const article = await getPublicArticle(id, lang);
    return {
      title: article.title,
      description: articleDescription(article),
      alternates: {
        canonical: `/articles/${article.id}`,
        languages: Object.fromEntries(article.available_languages.map((code) => [code, `/articles/${article.id}?lang=${code}`])),
      },
      openGraph: { type: "article", title: article.title, description: articleDescription(article), publishedTime: article.published_at },
    };
  } catch (error) {
    if (error instanceof Response && error.status === 404) return { title: "Article not found" };
    throw error;
  }
}

export default async function ArticlePage({ params, searchParams }: Props) {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  let article;
  try { article = await getPublicArticle(id, lang); }
  catch (error) { if (error instanceof Response && error.status === 404) notFound(); throw error; }
  const languages = await getPublicLanguages();
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: article.title,
    datePublished: article.published_at,
    dateModified: article.updated_at,
    inLanguage: article.language,
    articleSection: article.taxonomy,
    description: articleDescription(article),
    mainEntityOfPage: `${process.env.NEXT_PUBLIC_WEB_URL ?? "http://localhost:3000"}/articles/${article.id}`,
    publisher: { "@type": "Organization", name: process.env.NEXT_PUBLIC_SITE_NAME ?? "Signal Desk" },
  };
  return (
    <article className="article-page" dir={directionFor(article.direction)}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replaceAll("<", "\\u003c") }} />
      <header>
        <div className="eyebrow">{article.taxonomy.map((category) => <Link key={category} href={`/categories/${category}`}>{displayCategory(category)}</Link>)}</div>
        <h1>{article.title}</h1>
        {article.lead && <p className="article-lead">{article.lead}</p>}
        <div className="article-meta"><time dateTime={article.published_at}>{new Intl.DateTimeFormat(article.language, { dateStyle: "long", timeStyle: "short" }).format(new Date(article.published_at))}</time><span>{article.language.toUpperCase()} · {article.direction.toUpperCase()}</span></div>
        <nav className="language-links" aria-label="Available article languages">
          {article.available_languages.map((code) => <Link key={code} aria-current={code === article.language ? "page" : undefined} href={`/articles/${article.id}?lang=${code}`}>{code.toUpperCase()}</Link>)}
        </nav>
      </header>
      <div className="article-body">{(article.body || article.summary || "").split("\n").filter(Boolean).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div>
      {article.tags.length > 0 && <footer className="tag-list" aria-label="Tags">{article.tags.map((tag) => <span key={tag}>{tag}</span>)}</footer>}
      <span className="visually-hidden">Configured languages: {languages.map((item) => item.code).join(", ")}</span>
    </article>
  );
}
