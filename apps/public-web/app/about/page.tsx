import type { Metadata } from "next";
import { ServicePage } from "@/components/service-page";
import { publicRouteMetadata } from "@/lib/public-metadata";
import { serviceCopy } from "@/lib/service-content";

export async function generateMetadata({ searchParams }: { searchParams: Promise<{ lang?: string }> }): Promise<Metadata> { const { lang } = await searchParams; const copy = serviceCopy("about", lang); return publicRouteMetadata(`/about${copy.language === "en" ? "" : `?lang=${copy.language}`}`, copy.copy.title, "How Signal Desk publishes source-aware reporting.", { languages: ["en", "ar"] }); }

export default function AboutPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  return <ServicePage page="about" searchParams={searchParams} />;
}
