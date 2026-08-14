import type { Metadata } from "next";
import { ServicePage } from "@/components/service-page";
import { publicMetadata } from "@/lib/public-metadata";

export const metadata: Metadata = publicMetadata("/privacy", "Privacy Policy", "How Signal Desk handles public portal data.");

export default function PrivacyPage({ searchParams }: { searchParams: Promise<{ lang?: string }> }) {
  return <ServicePage title="Privacy Policy" eyebrow="Privacy" searchParams={searchParams}><p>We use the information needed to operate this public portal, keep it secure and understand its technical performance.</p><h2>Public browsing</h2><p>Public pages do not require an account. Server and security logs may contain limited technical request data for reliability and abuse prevention.</p><h2>Contact messages</h2><p>If you write to the newsroom, we use the details you provide to respond and process the request. We do not sell personal data.</p><h2>Updates</h2><p>This policy may change when the service changes. The current version is published on this page.</p></ServicePage>;
}
