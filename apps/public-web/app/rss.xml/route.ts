import { getPublicArticles } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET() {
  const articles = await getPublicArticles({ page_size: 100 });
  const base = process.env.NEXT_PUBLIC_WEB_URL ?? "http://localhost:3000";
  const name = process.env.NEXT_PUBLIC_SITE_NAME ?? "Signal Desk";
  const items = articles.items.map((article) => `<item><guid isPermaLink="true">${escapeXml(`${base}/articles/${article.id}`)}</guid><link>${escapeXml(`${base}/articles/${article.id}`)}</link><title>${escapeXml(article.title)}</title><description>${escapeXml(article.summary || article.lead || "")}</description><pubDate>${new Date(article.published_at).toUTCString()}</pubDate></item>`).join("");
  const xml = `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>${escapeXml(name)}</title><link>${escapeXml(base)}</link><description>Latest published reporting</description>${items}</channel></rss>`;
  return new Response(xml, { headers: { "Content-Type": "application/rss+xml; charset=utf-8", "Cache-Control": "public, max-age=60" } });
}

function escapeXml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&apos;");
}
