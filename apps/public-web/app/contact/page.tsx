import type { Metadata } from "next";
import { ServicePage } from "@/components/service-page";
import { publicMetadata } from "@/lib/public-metadata";

const contactEmail = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "editorial@example.invalid";
export const metadata: Metadata = publicMetadata("/contact", "Contact", "Contact the Signal Desk newsroom.");

export default function ContactPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  return <ServicePage title="Contact the newsroom" eyebrow="Contact" searchParams={searchParams}><p className="article-lead">For corrections, news tips and general editorial questions, contact the newsroom directly.</p><p><a href={`mailto:${contactEmail}`}>{contactEmail}</a></p><p>Please do not send sensitive personal data through ordinary email. We review messages as capacity allows.</p></ServicePage>;
}
