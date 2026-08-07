"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { PublicLanguage } from "@/lib/types";

export function LanguageSwitcher({ languages }: { languages: PublicLanguage[] }) {
  const pathname = usePathname();
  const search = useSearchParams();
  const router = useRouter();
  return (
    <label className="language-picker">
      <span>Language</span>
      <select
        aria-label="Article language"
        value={search.get("lang") ?? ""}
        onChange={(event) => {
          const next = new URLSearchParams(search.toString());
          if (event.target.value) next.set("lang", event.target.value);
          else next.delete("lang");
          router.push(`${pathname}${next.size ? `?${next}` : ""}`);
        }}
      >
        <option value="">Original</option>
        {languages.map((language) => (
          <option key={language.code} value={language.code}>
            {language.code.toUpperCase()} · {language.direction.toUpperCase()}
          </option>
        ))}
      </select>
    </label>
  );
}
