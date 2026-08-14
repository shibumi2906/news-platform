import type { Metadata } from "next";
import { ServicePage } from "@/components/service-page";
import { publicMetadata } from "@/lib/public-metadata";

export const metadata: Metadata = publicMetadata("/terms", "Terms", "Terms for using the Signal Desk public portal.");

export default function TermsPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  return <ServicePage title="Terms of use" eyebrow="Terms" searchParams={searchParams}><p>Use this public portal lawfully and respect applicable rights in the reporting, media and linked source material.</p><p>Published material is provided for information. Links to external sources do not imply their endorsement, and their availability is outside the newsroom’s control.</p><p>Do not attempt to disrupt the service, bypass access controls or misuse public endpoints.</p></ServicePage>;
}
