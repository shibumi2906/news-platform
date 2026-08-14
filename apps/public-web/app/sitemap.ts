import type { MetadataRoute } from "next";
import { getPublicArticles, getPublicCategories } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = process.env.NEXT_PUBLIC_WEB_URL ?? "http://localhost:3000";
  const [articles, categories] = await Promise.all([getPublicArticles({ page_size: 100 }), getPublicCategories()]);
  return [
    { url: base, changeFrequency: "hourly", priority: 1 },
    { url: `${base}/news`, changeFrequency: "hourly", priority: 0.9 },
    { url: `${base}/categories`, changeFrequency: "daily", priority: 0.7 },
    ...articles.items.map((article) => ({ url: `${base}/articles/${article.id}`, lastModified: article.updated_at, changeFrequency: "daily" as const, priority: 0.8 })),
    ...categories.map((category) => ({ url: `${base}/categories/${category.slug}`, changeFrequency: "daily" as const, priority: 0.6 })),
  ];
}
