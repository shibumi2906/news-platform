import type { Metadata } from "next";
import { ServicePage } from "@/components/service-page";
import { publicRouteMetadata } from "@/lib/public-metadata";
import { serviceCopy } from "@/lib/service-content";

export async function generateMetadata({ searchParams }: { searchParams: Promise<{ lang?: string }> }): Promise<Metadata> { const { lang } = await searchParams; const copy = serviceCopy("terms", lang); return publicRouteMetadata(`/terms${copy.language === "en" ? "" : `?lang=${copy.language}`}`, copy.copy.title, "Terms for using the Signal Desk public portal.", { languages: ["en", "ar"] }); }

export default function TermsPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  return <ServicePage page="terms" searchParams={searchParams} />;
}
