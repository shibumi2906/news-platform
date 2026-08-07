import Link from "next/link";

export default function NotFound() {
  return <section className="empty-state"><p className="kicker">404</p><h1>Article not found</h1><p>It may be unpublished or the address may be incorrect.</p><Link className="button-link" href="/news">Return to the news feed</Link></section>;
}
