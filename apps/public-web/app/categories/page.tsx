import type { Metadata } from "next";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { getPublicCategories } from "@/lib/api";
import { displayCategory } from "@/lib/presentation";
import { publicMetadata } from "@/lib/public-metadata";

export const metadata: Metadata = publicMetadata("/categories", "Topics", "Configured topics in published reporting.");

export default async function CategoriesPage() {
  const categories = await getPublicCategories();
  return <section className="section-block"><p className="kicker">Browse the desk</p><h1>Topics</h1>{categories.length ? <div className="topic-grid">{categories.map((category) => <Link key={category.slug} href={`/categories/${category.slug}`}><strong>{displayCategory(category.slug)}</strong><span>{category.article_count} articles</span></Link>)}</div> : <EmptyState title="No topics yet" detail="Topics appear when articles are published." />}</section>;
}
