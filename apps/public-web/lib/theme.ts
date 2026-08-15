export const publicThemes = ["editorial", "midnight", "signal"] as const;

export type PublicTheme = (typeof publicThemes)[number];

export const defaultPublicTheme: PublicTheme = "editorial";

export function resolvePublicTheme(value = process.env.NEXT_PUBLIC_PORTAL_THEME): PublicTheme {
  const normalized = value?.trim().toLowerCase();
  return publicThemes.includes(normalized as PublicTheme)
    ? (normalized as PublicTheme)
    : defaultPublicTheme;
}

export function publicThemeAttributes(value?: string): { "data-theme": PublicTheme } {
  return { "data-theme": resolvePublicTheme(value) };
}
