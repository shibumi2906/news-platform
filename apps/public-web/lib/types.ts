export type Direction = "ltr" | "rtl";

export interface PublicArticle {
  id: string;
  article_version_id: string;
  title: string;
  lead: string | null;
  body: string | null;
  summary: string | null;
  tags: string[];
  taxonomy: string[];
  language: string;
  direction: Direction;
  available_languages: string[];
  published_at: string;
  updated_at: string;
  facts: Record<string, unknown>[];
  entities: Record<string, unknown>[];
  sources: Record<string, unknown>[];
}

export interface PublicArticlePage {
  items: PublicArticle[];
  page: number;
  page_size: number;
  total: number;
}

export interface PublicEvent {
  id: string;
  title: string;
  summary: string | null;
  taxonomy: string[];
  latest_published_at: string;
  article_count: number;
}

export interface PublicEventDetail extends PublicEvent {
  articles: PublicArticle[];
}

export interface PublicCategory {
  slug: string;
  article_count: number;
}

export interface PublicLanguage {
  code: string;
  direction: Direction;
}

export interface AdminArticle {
  id: string;
  status: string;
  lock_version: number;
  latest_version_number: number;
  four_eyes_required: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdminArticleDetail extends AdminArticle {
  versions: Array<Record<string, unknown>>;
  translations: Array<Record<string, unknown>>;
  tasks: Array<Record<string, unknown>>;
  reviews: Array<Record<string, unknown>>;
  publication: Record<string, unknown> | null;
}
