import type { Metadata } from "next";
import { ServicePage } from "@/components/service-page";
import { publicRouteMetadata } from "@/lib/public-metadata";
import { serviceCopy } from "@/lib/service-content";

export async function generateMetadata({ searchParams }: { searchParams: Promise<{ lang?: string }> }): Promise<Metadata> { const { lang } = await searchParams; const copy = serviceCopy("editorial-policy", lang); return publicRouteMetadata(`/editorial-policy${copy.language === "en" ? "" : `?lang=${copy.language}`}`, copy.copy.title, "How the Signal Desk newsroom reviews and corrects reporting.", { languages: ["en", "ar"] }); }

export default function EditorialPolicyPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  return <ServicePage page="editorial-policy" searchParams={searchParams} />;
}
