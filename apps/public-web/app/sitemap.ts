import type { MetadataRoute } from "next";
import { getAllPublicArticles, getPublicCategories, getPublicEntities, getPublicEvents, getPublicRegions } from "@/lib/api";
import { publicServicePaths } from "@/lib/public-metadata";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = process.env.NEXT_PUBLIC_WEB_URL ?? "http://localhost:3000";
  const [articles, categories, regions, events, entities] = await Promise.all([getAllPublicArticles(), getPublicCategories(), getPublicRegions(), getPublicEvents(), getPublicEntities()]);
  return [
    { url: base, changeFrequency: "hourly", priority: 1 },
    { url: `${base}/news`, changeFrequency: "hourly", priority: 0.9 },
    { url: `${base}/categories`, changeFrequency: "daily", priority: 0.7 },
    { url: `${base}/regions`, changeFrequency: "daily", priority: 0.7 },
    { url: `${base}/events`, changeFrequency: "daily", priority: 0.7 },
    { url: `${base}/entities`, changeFrequency: "daily", priority: 0.7 },
    ...publicServicePaths.map((path) => ({ url: `${base}${path}`, changeFrequency: "monthly" as const, priority: 0.3 })),
    ...articles.map((article) => ({ url: `${base}/articles/${article.id}`, lastModified: article.updated_at, changeFrequency: "daily" as const, priority: 0.8 })),
    ...categories.map((category) => ({ url: `${base}/categories/${category.slug}`, changeFrequency: "daily" as const, priority: 0.6 })),
    ...regions.map((region) => ({ url: `${base}/regions/${encodeURIComponent(region.slug)}`, changeFrequency: "daily" as const, priority: 0.6 })),
    ...events.map((event) => ({ url: `${base}/events/${event.id}`, lastModified: event.latest_published_at, changeFrequency: "daily" as const, priority: 0.6 })),
    ...entities.map((entity) => ({ url: `${base}/entities/${entity.id}`, lastModified: entity.latest_published_at, changeFrequency: "daily" as const, priority: 0.6 })),
  ];
}
