import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getPublicArticle, getPublicLanguages } from "@/lib/api";
import { articleDescription, directionFor, displayCategory } from "@/lib/presentation";
import { publicRouteMetadata, publicUrl, siteName } from "@/lib/public-metadata";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ lang?: string }> };

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  try {
    const article = await getPublicArticle(id, lang);
    return { ...publicRouteMetadata(`/articles/${article.id}`, article.title, articleDescription(article), { languages: article.available_languages, type: "article" }), openGraph: { type: "article", url: `/articles/${article.id}`, siteName, title: article.title, description: articleDescription(article), publishedTime: article.published_at, modifiedTime: article.updated_at } };
  } catch (error) {
    if (error instanceof Response && error.status === 404) return { title: "Article not found" };
    if (error instanceof Response && error.status === 410) return { title: "Article no longer available", robots: { index: false, follow: true } };
    throw error;
  }
}

export default async function ArticlePage({ params, searchParams }: Props) {
  const [{ id }, { lang }] = await Promise.all([params, searchParams]);
  let article;
  try { article = await getPublicArticle(id, lang); }
  catch (error) {
    if (error instanceof Response && error.status === 404) notFound();
    if (error instanceof Response && error.status === 410) return <section className="empty-state"><p className="kicker">410</p><h1>Article no longer available</h1><p>This article was permanently unpublished and is no longer part of the public record.</p><Link className="button-link" href="/news">Return to the news feed</Link></section>;
    throw error;
  }
  const languages = await getPublicLanguages();
  const sourceUrls = article.sources.map((source) => source.url).filter((url): url is string => typeof url === "string" && /^https?:\/\//i.test(url));
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: article.title,
    datePublished: article.published_at,
    dateModified: article.updated_at,
    inLanguage: article.language,
    articleSection: article.taxonomy,
    description: articleDescription(article),
    mainEntityOfPage: `${publicUrl}/articles/${article.id}`,
    publisher: { "@type": "Organization", name: siteName },
    ...(sourceUrls.length ? { citation: sourceUrls, isBasedOn: sourceUrls[0] } : {}),
  };
  const breadcrumbs = { "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement: [{ "@type": "ListItem", position: 1, name: "Home", item: publicUrl }, { "@type": "ListItem", position: 2, name: "News", item: `${publicUrl}/news` }, { "@type": "ListItem", position: 3, name: article.title, item: `${publicUrl}/articles/${article.id}` }] };
  return (
    <article className="article-page" dir={directionFor(article.direction)}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replaceAll("<", "\\u003c") }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbs).replaceAll("<", "\\u003c") }} />
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
      {sourceUrls.length > 0 && <section className="source-attribution" aria-labelledby="sources-heading"><h2 id="sources-heading">Sources</h2><ul>{sourceUrls.map((url) => <li key={url}><a href={url} rel="noreferrer" target="_blank">{url}</a></li>)}</ul></section>}
      <span className="visually-hidden">Configured languages: {languages.map((item) => item.code).join(", ")}</span>
    </article>
  );
}
