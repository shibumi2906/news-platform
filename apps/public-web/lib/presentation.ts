import type { Direction, PublicArticle } from "@/lib/types";

export const directionFor = (direction: string): Direction =>
  direction === "rtl" ? "rtl" : "ltr";

export function articleDescription(article: PublicArticle): string {
  return article.summary || article.lead || article.body?.slice(0, 160) || article.title;
}

export function displayCategory(slug: string): string {
  return slug
    .split("-")
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}
