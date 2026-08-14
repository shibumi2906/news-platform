import type { Metadata } from "next";
import Link from "next/link";
import { ServicePage } from "@/components/service-page";
import { publicMetadata } from "@/lib/public-metadata";

export const metadata: Metadata = publicMetadata("/editorial-policy", "Editorial Policy", "How the Signal Desk newsroom reviews and corrects reporting.");

export default function EditorialPolicyPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  return <ServicePage title="Editorial Policy" eyebrow="About the newsroom" searchParams={searchParams}><p className="article-lead">The newsroom separates collection, processing and editorial publication. Only published versions are public.</p><h2>Sources and review</h2><p>Reporting is assembled from configured sources and undergoes editorial review before publication. A source link is not itself an endorsement or a final fact determination.</p><h2>Corrections</h2><p>When a meaningful error is identified, editors create a corrected version and retain the editorial history. Send correction requests through the <Link href="/contact">contact page</Link>.</p><h2>Independence</h2><p>Topic and category choices are managed by the newsroom configuration. Editorial decisions are not automated publication decisions.</p></ServicePage>;
}
