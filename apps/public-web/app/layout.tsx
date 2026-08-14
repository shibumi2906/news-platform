import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { publicUrl, siteName } from "@/lib/public-metadata";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  metadataBase: new URL(publicUrl),
  title: { default: siteName, template: `%s · ${siteName}` },
  description: "Independent, source-aware reporting from the News Platform.",
  alternates: { canonical: "/", types: { "application/rss+xml": "/rss.xml" } },
  robots: { index: true, follow: true },
  openGraph: { type: "website", url: "/", siteName, title: siteName, description: "Independent, source-aware reporting from the News Platform." },
  twitter: { card: "summary", title: siteName, description: "Independent, source-aware reporting from the News Platform." },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" dir="ltr">
      <body>
        <a className="skip-link" href="#main-content">Skip to content</a>
        <header className="site-header">
          <Link className="wordmark" href="/">{siteName}</Link>
          <nav aria-label="Primary navigation">
            <Link href="/news">News</Link>
            <Link href="/events">Events</Link>
            <Link href="/entities">Entities</Link>
            <Link href="/categories">Topics</Link>
            <Link href="/admin">Admin</Link>
          </nav>
        </header>
        <main id="main-content">{children}</main>
        <footer className="site-footer">
          <span>{siteName}</span>
          <Link href="/about">About</Link>
          <Link href="/contact">Contact</Link>
          <Link href="/editorial-policy">Editorial Policy</Link>
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <Link href="/rss.xml">RSS</Link>
        </footer>
      </body>
    </html>
  );
}
