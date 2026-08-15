import type { Metadata } from "next";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { getPublicRegions } from "@/lib/api";
import { publicMetadata } from "@/lib/public-metadata";

export const metadata: Metadata = publicMetadata("/regions", "Regions", "Published reporting by newsroom-configured region.");

export default async function RegionsPage() {
  const regions = await getPublicRegions();
  return <section className="section-block"><p className="kicker">Browse the desk</p><h1>Regions</h1>{regions.length ? <div className="topic-grid">{regions.map((region) => <Link key={region.slug} href={`/regions/${encodeURIComponent(region.slug)}`}><strong>{region.slug}</strong><span>{region.article_count} articles</span></Link>)}</div> : <EmptyState title="No regions yet" detail="Regions appear when configured regional reporting is published." />}</section>;
}
