import type { Metadata } from "next";

export const siteName = process.env.NEXT_PUBLIC_SITE_NAME ?? "Signal Desk";
export const publicUrl = process.env.NEXT_PUBLIC_WEB_URL ?? "http://localhost:3000";
export const publicServicePaths = ["/about", "/contact", "/privacy", "/terms", "/editorial-policy"] as const;

export function languageAlternates(path: string, languages: readonly string[]): Record<string, string> {
  const entries = languages.map((language) => [language, `${path}?lang=${encodeURIComponent(language)}`] as const);
  return Object.fromEntries([...entries, ["x-default", path]]);
}

export function publicRouteMetadata(
  path: string,
  title: string,
  description: string,
  options: { languages?: readonly string[]; noindex?: boolean; type?: "website" | "article" } = {},
): Metadata {
  return {
    title,
    description,
    alternates: { canonical: path, ...(options.languages?.length ? { languages: languageAlternates(path, options.languages) } : {}) },
    robots: options.noindex ? { index: false, follow: true } : undefined,
    openGraph: { type: options.type ?? "website", url: path, siteName, title, description },
    twitter: { card: "summary", title, description },
  };
}

export function publicMetadata(path: string, title: string, description: string): Metadata {
  return publicRouteMetadata(path, title, description);
}
