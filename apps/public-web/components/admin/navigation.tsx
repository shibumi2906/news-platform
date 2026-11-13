"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function AdminNavigation({ links, "aria-label": label }: {
  links: ReadonlyArray<readonly [string, string, string | null]>;
  "aria-label": string;
}) {
  const path = usePathname();
  return <nav aria-label={label}>{links.map(([name, href]) => (
    <Link key={href} href={href} aria-current={path === href || (href !== "/admin" && path.startsWith(href + "/")) ? "page" : undefined}>
      {name}
    </Link>
  ))}</nav>;
}
