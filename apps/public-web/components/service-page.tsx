import Link from "next/link";
import type { ReactNode } from "react";
import { getPublicLanguages } from "@/lib/api";

export async function ServicePage({
  title,
  eyebrow,
  children,
  searchParams,
}: {
  title: string;
  eyebrow: string;
  children: ReactNode;
  searchParams: Promise<{ lang?: string }>;
}) {
  const { lang } = await searchParams;
  const languages = await getPublicLanguages();
  const active = languages.find((language) => language.code === lang);
  return <section className="section-block service-page" lang={lang ?? "en"} dir={active?.direction ?? "ltr"}><header className="section-heading"><div><p className="kicker">{eyebrow}</p><h1>{title}</h1></div><nav className="language-links" aria-label="Page language">{languages.map((language) => <Link key={language.code} aria-current={language.code === lang ? "page" : undefined} href={`?lang=${encodeURIComponent(language.code)}`}>{language.code.toUpperCase()}</Link>)}</nav></header><div className="service-page-content">{children}</div></section>;
}
