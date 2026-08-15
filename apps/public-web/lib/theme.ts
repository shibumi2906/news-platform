export const PUBLIC_THEME_CONTRACT_VERSION = "1.0" as const;

export const publicThemeManifest = {
  contractVersion: PUBLIC_THEME_CONTRACT_VERSION,
  defaultTheme: "editorial",
  themes: {
    editorial: { colorScheme: "light", layout: "newspaper", cssSelector: 'html[data-theme="editorial"]' },
    midnight: { colorScheme: "dark", layout: "magazine", cssSelector: 'html[data-theme="midnight"]' },
    signal: { colorScheme: "light", layout: "cards", cssSelector: 'html[data-theme="signal"]' },
  },
} as const;

export const publicThemes = Object.keys(publicThemeManifest.themes) as Array<keyof typeof publicThemeManifest.themes>;
export type PublicTheme = (typeof publicThemes)[number];
export const defaultPublicTheme: PublicTheme = publicThemeManifest.defaultTheme;

export function resolvePublicTheme(value = process.env.NEXT_PUBLIC_PORTAL_THEME): PublicTheme {
  const normalized = value?.trim().toLowerCase();
  return publicThemes.includes(normalized as PublicTheme) ? (normalized as PublicTheme) : defaultPublicTheme;
}

export function publicThemeAttributes(value?: string): { "data-theme": PublicTheme } {
  return { "data-theme": resolvePublicTheme(value) };
}
