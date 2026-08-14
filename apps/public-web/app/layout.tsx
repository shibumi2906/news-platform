import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

const siteName = process.env.NEXT_PUBLIC_SITE_NAME ?? "Signal Desk";
const publicUrl = process.env.NEXT_PUBLIC_WEB_URL ?? "http://localhost:3000";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  metadataBase: new URL(publicUrl),
  title: { default: siteName, template: `%s · ${siteName}` },
  description: "Independent, source-aware reporting from the News Platform.",
  alternates: { types: { "application/rss+xml": "/rss.xml" } },
  robots: { index: true, follow: true },
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
          <Link href="/rss.xml">RSS</Link>
        </footer>
      </body>
    </html>
  );
}
