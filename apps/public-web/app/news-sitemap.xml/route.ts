import { getAllPublicArticles } from "@/lib/api";
import { publicUrl } from "@/lib/public-metadata";

export const dynamic = "force-dynamic";

export async function GET() {
  const articles = await getAllPublicArticles();
  const items = articles.slice(0, 1000).map((article) => `<url><loc>${escapeXml(`${publicUrl}/articles/${article.id}`)}</loc><news:news><news:publication><news:name>${escapeXml(process.env.NEXT_PUBLIC_SITE_NAME ?? "Signal Desk")}</news:name><news:language>${escapeXml(article.language.split("-")[0] || "en")}</news:language></news:publication><news:publication_date>${article.published_at}</news:publication_date><news:title>${escapeXml(article.title)}</news:title></news:news></url>`).join("");
  return new Response(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">${items}</urlset>`, { headers: { "Content-Type": "application/xml; charset=utf-8" } });
}

function escapeXml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&apos;");
}
