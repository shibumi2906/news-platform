import Link from "next/link";
import { serviceCopy, serviceLanguages, type ServicePageKey } from "@/lib/service-content";

export async function ServicePage({
  page,
  searchParams,
}: {
  page: ServicePageKey;
  searchParams: Promise<{ lang?: string }>;
}) {
  const { lang } = await searchParams;
  const localized = serviceCopy(page, lang);
  const contactEmail = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "editorial@example.invalid";
  return <section className="section-block service-page" lang={localized.language} dir={localized.direction}><header className="section-heading"><div><p className="kicker">{localized.copy.eyebrow}</p><h1>{localized.copy.title}</h1></div><nav className="language-links" aria-label="Page language">{serviceLanguages.map((language) => <Link key={language} aria-current={language === localized.language ? "page" : undefined} href={`?lang=${language}`}>{language.toUpperCase()}</Link>)}</nav></header><div className="service-page-content">{localized.copy.lead && <p className="article-lead">{localized.copy.lead}</p>}{page === "contact" && <p><a href={`mailto:${contactEmail}`}>{contactEmail}</a></p>}{localized.copy.sections.map((section) => <section key={section.text}>{section.heading && <h2>{section.heading}</h2>}<p>{section.text}</p></section>)}</div></section>;
}
