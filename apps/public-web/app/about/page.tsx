import type { Metadata } from "next";
import { ServicePage } from "@/components/service-page";
import { publicMetadata } from "@/lib/public-metadata";

export const metadata: Metadata = publicMetadata("/about", "About", "How Signal Desk publishes source-aware reporting.");

export default function AboutPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  return <ServicePage title="About Signal Desk" eyebrow="Public interest reporting" searchParams={searchParams}><p className="article-lead">Signal Desk is an editorially controlled public newsroom for reporting built from traceable sources.</p><p>We publish only reviewed material and keep the public portal focused on articles, their related events and the entities they discuss.</p><p>Coverage and topics are configured by the newsroom. Publication choices remain human decisions.</p></ServicePage>;
}
