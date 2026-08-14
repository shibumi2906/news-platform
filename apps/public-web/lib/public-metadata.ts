import type { Metadata } from "next";

export const siteName = process.env.NEXT_PUBLIC_SITE_NAME ?? "Signal Desk";
export const publicUrl = process.env.NEXT_PUBLIC_WEB_URL ?? "http://localhost:3000";
export const publicServicePaths = ["/about", "/contact", "/privacy", "/terms", "/editorial-policy"] as const;

export function publicMetadata(path: string, title: string, description: string): Metadata {
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: "website", url: path, siteName, title, description },
    twitter: { card: "summary", title, description },
  };
}
