"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

async function mutate(system: "site" | "integrator", path: string, method: string, body: unknown) {
  const response = await fetch(`/api/admin/${system}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string; error?: { message?: string } } | null;
    throw new Error(payload?.error?.message || payload?.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

function MutationForm({ children, onSubmit, label }: { children: ReactNode; onSubmit: (data: FormData) => Promise<void>; label: string }) {
  const [message, setMessage] = useState<string>();
  const [pending, setPending] = useState(false);
  const router = useRouter();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPending(true); setMessage(undefined);
    try { await onSubmit(new FormData(event.currentTarget)); setMessage("Saved"); event.currentTarget.reset(); router.refresh(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Request failed"); }
    finally { setPending(false); }
  }
  return <form className="admin-form" onSubmit={submit}>{children}<button disabled={pending} type="submit">{pending ? "Working…" : label}</button>{message && <p className={message === "Saved" ? "form-success" : "form-error"} role="status">{message}</p>}</form>;
}

export function SourceCreateForm() {
  return <MutationForm label="Add source" onSubmit={(data) => mutate("integrator", "/api/v1/sources", "POST", { name: data.get("name"), feed_url: data.get("feed_url"), adapter_type: data.get("adapter_type"), poll_interval_seconds: Number(data.get("poll_interval_seconds")) }).then(() => undefined)}><label>Name<input name="name" required /></label><label>Feed or page URL<input name="feed_url" type="url" required /></label><label>Adapter<select name="adapter_type"><option value="rss">RSS / Atom</option><option value="html">HTTP / HTML</option></select></label><label>Poll interval, seconds<input name="poll_interval_seconds" type="number" min="30" defaultValue="300" required /></label></MutationForm>;
}

export function SourceStateButton({ id, active }: { id: string; active: boolean }) {
  return <MutationForm label={active ? "Deactivate" : "Activate"} onSubmit={() => mutate("integrator", `/api/v1/sources/${id}/${active ? "deactivate" : "activate"}`, "POST", {}).then(() => undefined)}><span className="visually-hidden">Change source state</span></MutationForm>;
}

export function TopicCreateForm() {
  return <MutationForm label="Create topic" onSubmit={async (data) => { const categories = JSON.parse(String(data.get("categories") || "[]")) as unknown; await mutate("integrator", "/api/v1/ai/topics", "POST", { name: data.get("name"), slug: data.get("slug"), description: data.get("description") || null, categories, keywords: String(data.get("keywords") || "").split(",").map((v) => v.trim()).filter(Boolean), exclusions: [], regions: [], priority: Number(data.get("priority") || 0), relevance_threshold: Number(data.get("threshold") || .5), additional_rules: {}, is_active: true }); }}><label>Name<input name="name" required /></label><label>Slug<input name="slug" pattern="[a-z0-9][a-z0-9-]*" required /></label><label>Description<textarea name="description" /></label><label>Keywords, comma-separated<input name="keywords" /></label><label>Categories JSON<textarea name="categories" defaultValue='[{"name":"News","slug":"news","keywords":[]}]' required /></label><div className="form-row"><label>Priority<input name="priority" type="number" defaultValue="0" /></label><label>Threshold<input name="threshold" type="number" min="0" max="1" step="0.05" defaultValue="0.5" /></label></div></MutationForm>;
}

export function LanguageToggle({ language }: { language: { code: string; name: string; direction: string; priority: number; is_active: boolean; translation_enabled: boolean } }) {
  return <MutationForm label={language.translation_enabled ? "Disable translation" : "Enable translation"} onSubmit={() => mutate("integrator", `/api/v1/ai/languages/${language.code}`, "PUT", { ...language, translation_enabled: !language.translation_enabled }).then(() => undefined)}><span className="visually-hidden">Toggle {language.name}</span></MutationForm>;
}

export function TerminologyCreateForm({ languages }: { languages: Array<{ code: string; name: string }> }) {
  return <MutationForm label="Add term" onSubmit={(data) => mutate("integrator", "/api/v1/ai/terminology", "POST", { source_language_code: data.get("source"), target_language_code: data.get("target"), source_term: data.get("source_term"), target_term: data.get("target_term"), notes: data.get("notes") || null, is_active: true }).then(() => undefined)}><div className="form-row"><label>Source language<select name="source">{languages.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label><label>Target language<select name="target">{languages.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label></div><label>Source term<input name="source_term" required /></label><label>Approved translation<input name="target_term" required /></label><label>Notes<textarea name="notes" /></label></MutationForm>;
}

export function CreateArticleButton({ packageVersionId }: { packageVersionId: string }) {
  return <MutationForm label="Create article" onSubmit={() => mutate("site", "/api/v1/articles", "POST", { incoming_package_version_id: packageVersionId }).then(() => undefined)}><span className="visually-hidden">Create an editorial draft</span></MutationForm>;
}

export function ArticleWorkflow({ article }: { article: { id: string; status: string; lock_version: number } }) {
  const action = (path: string, body: Record<string, unknown> = {}) => mutate("site", `/api/v1/articles/${article.id}${path}`, "POST", { expected_lock_version: article.lock_version, ...body }).then(() => undefined);
  return <div className="workflow-actions">{article.status === "draft" && <MutationForm label="Submit for review" onSubmit={() => action("/submit-review")}><span /></MutationForm>}{article.status === "needs_review" && <><MutationForm label="Approve" onSubmit={() => action("/reviews/approve", { reason: "Approved in Admin UI" })}><span /></MutationForm><MutationForm label="Reject" onSubmit={() => action("/reviews/reject", { reason: "Rejected in Admin UI" })}><span /></MutationForm></>}{article.status === "approved" && <><MutationForm label="Publish now" onSubmit={() => action("/publication", { scheduled_at: null })}><span /></MutationForm><MutationForm label="Schedule" onSubmit={(data) => action("/publication", { scheduled_at: data.get("scheduled_at") })}><label>UTC publication time<input type="datetime-local" name="scheduled_at" required /></label></MutationForm></>}{article.status === "published" && <MutationForm label="Unpublish" onSubmit={() => action("/unpublish", { reason: "Unpublished in Admin UI" })}><span /></MutationForm>}</div>;
}

export function ArticleVersionForm({ article }: { article: { id: string; lock_version: number; versions: Array<Record<string, unknown>> } }) {
  const latest = article.versions[0]?.content ?? {};
  return <MutationForm label="Create immutable version" onSubmit={async (data) => { const content = JSON.parse(String(data.get("content"))) as unknown; await mutate("site", `/api/v1/articles/${article.id}/versions`, "POST", { content, expected_lock_version: article.lock_version, correction_explanation: data.get("correction_explanation") || null }); }}><label>Version content JSON<textarea name="content" rows={12} defaultValue={JSON.stringify(latest, null, 2)} required /></label><label>Correction explanation<input name="correction_explanation" /></label></MutationForm>;
}
