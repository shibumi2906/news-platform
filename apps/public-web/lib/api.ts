import type {
  AdminArticle,
  AdminArticleDetail,
  PublicArticle,
  PublicCategory,
  PublicLanguage,
} from "@/lib/types";
import { cookies } from "next/headers";
import { requireSession, SESSION_COOKIE } from "@/lib/session";

const siteUrl = process.env.SITE_API_URL ?? "http://localhost:8002";
const integratorUrl = process.env.INTEGRATOR_API_URL ?? "http://localhost:8001";

async function requestJson<T>(
  baseUrl: string,
  path: string,
  options: RequestInit & { admin?: boolean; revalidate?: number } = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.admin) {
    await requireSession();
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!token) throw new Error("Admin session is required for admin API calls");
    headers.set("X-Admin-Session", token);
  }
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers,
    cache: options.admin ? "no-store" : undefined,
    next: options.admin ? undefined : { revalidate: options.revalidate ?? 60 },
  });
  if (!response.ok) {
    if (response.status === 404) throw new Response("Not found", { status: 404 });
    throw new Error(`API request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function getPublicArticles(language?: string, category?: string): Promise<PublicArticle[]> {
  const search = new URLSearchParams();
  if (language) search.set("language", language);
  if (category) search.set("category", category);
  const suffix = search.size ? `?${search}` : "";
  return requestJson(siteUrl, `/api/v1/public/articles${suffix}`);
}

export function getPublicArticle(id: string, language?: string): Promise<PublicArticle> {
  const suffix = language ? `?language=${encodeURIComponent(language)}` : "";
  return requestJson(siteUrl, `/api/v1/public/articles/${encodeURIComponent(id)}${suffix}`);
}

export function getPublicCategories(): Promise<PublicCategory[]> {
  return requestJson(siteUrl, "/api/v1/public/categories");
}

export function getPublicLanguages(): Promise<PublicLanguage[]> {
  return requestJson(siteUrl, "/api/v1/public/languages");
}

export function getAdminSite<T>(path: string): Promise<T> {
  return requestJson<T>(siteUrl, path, { admin: true });
}

export function getAdminIntegrator<T>(path: string): Promise<T> {
  return requestJson<T>(integratorUrl, path, { admin: true });
}

export const getAdminArticles = (): Promise<AdminArticle[]> =>
  getAdminSite("/api/v1/admin/articles");

export const getAdminArticle = (id: string): Promise<AdminArticleDetail> =>
  getAdminSite(`/api/v1/admin/articles/${encodeURIComponent(id)}`);

export function backendUrl(system: "site" | "integrator"): string {
  return system === "site" ? siteUrl : integratorUrl;
}
