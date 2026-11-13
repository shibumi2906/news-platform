"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

export async function mutate(system: "site" | "integrator", path: string, method: string, body: unknown) {
  const csrf = document.cookie.split("; ").find((item) => item.startsWith("news_admin_csrf="))?.split("=", 2)[1];
  const response = await fetch(`/api/admin/${system}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {}) },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string; error?: { message?: string } } | null;
    throw new Error(payload?.error?.message || (typeof payload?.detail === "string" ? payload.detail : undefined) || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

export function MutationForm({ children, onSubmit, label, resetOnSuccess = true }: { children: ReactNode; onSubmit: (data: FormData) => Promise<void>; label: string; resetOnSuccess?: boolean }) {
  const [message, setMessage] = useState<string>();
  const [pending, setPending] = useState(false);
  const router = useRouter();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPending(true); setMessage(undefined);
    const form = event.currentTarget;
    try { await onSubmit(new FormData(form)); setMessage("Saved"); if (resetOnSuccess) form.reset(); router.refresh(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Request failed"); }
    finally { setPending(false); }
  }
  return <form className="admin-form" onSubmit={submit}>{children}<button disabled={pending} type="submit">{pending ? "Working…" : label}</button>{message && <p className={message === "Saved" ? "form-success" : "form-error"} role="status">{message}</p>}</form>;
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

export function MediaUploadForm() {
  return <MutationForm label="Upload original" onSubmit={async (data) => {
    const file = data.get("file");
    if (!(file instanceof File) || !file.size) throw new Error("Choose a media file");
    const content = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("Could not read file"));
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
      reader.readAsDataURL(file);
    });
    await mutate("site", "/api/v1/admin/media", "POST", {
      content_base64: content, mime_type: file.type, kind: "original",
      rights: { license: data.get("license"), attribution: data.get("attribution"), allowed_uses: ["editorial", "distribution"] },
      provenance: { source: "admin_upload", original_name: file.name },
    });
  }}><label>Media file<input name="file" type="file" accept="image/*,video/*,audio/*" required /></label><label>License<input name="license" required /></label><label>Attribution<input name="attribution" /></label></MutationForm>;
}

export function MediaGenerateForm() {
  return <MutationForm label="Generate variants" onSubmit={(data) => mutate("site", "/api/v1/admin/media/generate", "POST", { article_version_id: data.get("article_version_id"), variants: Number(data.get("variants") || 3) }).then(() => undefined)}><label>Immutable article version ID<input name="article_version_id" required /></label><label>Variants<input name="variants" type="number" min="1" max="4" defaultValue="3" /></label></MutationForm>;
}

export function MediaSelectForm({ assetId }: { assetId: string }) {
  return <MutationForm label="Select & link" onSubmit={(data) => mutate("site", `/api/v1/admin/media/${assetId}/select`, "POST", { article_version_id: data.get("article_version_id"), translation_version_id: data.get("translation_version_id") || null, role: data.get("role") || "hero" }).then(() => undefined)}><label>Article version ID<input name="article_version_id" required /></label><label>Translation version ID (optional)<input name="translation_version_id" /></label><label>Role<select name="role"><option value="hero">Hero</option><option value="inline">Inline</option><option value="social">Social</option></select></label></MutationForm>;
}

export function MemeTemplateForm() {
  return <MutationForm label="Create template" onSubmit={(data) => mutate("site", "/api/v1/admin/media/meme-templates", "POST", { name: data.get("name"), base_asset_id: data.get("base_asset_id"), layout: { caption_position: data.get("caption_position") } }).then(() => undefined)}><label>Name<input name="name" required /></label><label>Base asset ID<input name="base_asset_id" required /></label><label>Caption position<select name="caption_position"><option value="bottom">Bottom</option><option value="top">Top</option></select></label></MutationForm>;
}

export function MemeGenerateForm() {
  return <MutationForm label="Create meme version" onSubmit={(data) => mutate("site", "/api/v1/admin/media/memes", "POST", { template_id: data.get("template_id"), article_version_id: data.get("article_version_id"), mode: data.get("mode"), caption: data.get("caption") || null }).then(() => undefined)}><label>Template ID<input name="template_id" required /></label><label>Article version ID<input name="article_version_id" required /></label><label>Mode<select name="mode"><option value="manual">Manual</option><option value="ai">AI caption</option></select></label><label>Manual caption<textarea name="caption" maxLength={280} /></label></MutationForm>;
}

export function VideoProjectForm() {
  return <MutationForm label="Create script & storyboard" onSubmit={(data) => mutate("site", "/api/v1/admin/media/video-projects", "POST", { article_version_id: data.get("article_version_id") }).then(() => undefined)}><label>Article version ID<input name="article_version_id" required /></label></MutationForm>;
}

export function DistributionChannelForm() {
  return <MutationForm label="Add channel" onSubmit={(data) => { const kind = String(data.get("kind")); const config: Record<string, FormDataEntryValue> = {}; for (const key of ["chat_id", "page_id", "instagram_account_id", "channel_id", "media_url_template", "article_url_template"]) { const value = data.get(key); if (value) config[key] = value; } return mutate("site", "/api/v1/admin/distribution/channels", "POST", { name: data.get("name"), kind, account_key: data.get("account_key"), credential_ref: data.get("credential_ref") || null, config }).then(() => undefined); }}><label>Name<input name="name" required /></label><label>Provider<select name="kind"><option value="telegram">Telegram</option><option value="facebook">Facebook Page</option><option value="instagram">Instagram</option><option value="tiktok">TikTok</option><option value="x">X</option><option value="youtube">YouTube</option></select></label><p>Each provider requires an OAuth access token in the named server environment variable.</p><label>Account key<input name="account_key" required /></label><label>Credential env reference<input name="credential_ref" required pattern="[A-Z0-9_]+" placeholder="PRODUCTION_PROVIDER_TOKEN" /></label><label>Telegram chat ID<input name="chat_id" /></label><label>Facebook page ID<input name="page_id" /></label><label>Instagram account ID<input name="instagram_account_id" /></label><label>YouTube channel ID<input name="channel_id" /></label><label>Public media URL template<input name="media_url_template" type="url" placeholder="https://cdn.example/media/{asset_id}" /></label><label>Public article URL template<input name="article_url_template" type="url" placeholder="https://news.example/articles/{article_id}" /></label></MutationForm>;
}

export function DistributionScheduleForm({ channels }: { channels: Array<{ id: string; name: string; kind: string }> }) {
  return <MutationForm label="Schedule delivery" onSubmit={(data) => mutate("site", "/api/v1/admin/distribution/jobs", "POST", { channel_id: data.get("channel_id"), article_version_id: data.get("article_version_id"), translation_version_id: data.get("translation_version_id") || null, media_asset_id: data.get("media_asset_id") || null, scheduled_at: data.get("scheduled_at") || null, idempotency_key: data.get("idempotency_key") || null, max_attempts: 5 }).then(() => undefined)}><label>Channel<select name="channel_id" required>{channels.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.kind}</option>)}</select></label><label>Published article version ID<input name="article_version_id" required /></label><label>Translation version ID<input name="translation_version_id" /></label><label>Media asset ID<input name="media_asset_id" /></label><label>Schedule (UTC)<input type="datetime-local" name="scheduled_at" /></label><label>Idempotency key (optional)<input name="idempotency_key" minLength={8} /></label></MutationForm>;
}

export function DistributionChannelState({ id, active }: { id: string; active: boolean }) {
  return <MutationForm label={active ? "Deactivate" : "Activate"} onSubmit={() => mutate("site", `/api/v1/admin/distribution/channels/${id}/${active ? "deactivate" : "activate"}`, "POST", {}).then(() => undefined)}><span /></MutationForm>;
}

export function UserCreateForm({ roles }: { roles: Array<{ id: string; name: string }> }) {
  return <MutationForm label="Create user" onSubmit={(data) => mutate("site", "/api/v1/admin/security/users", "POST", {
    username: data.get("username"), display_name: data.get("display_name"), password: data.get("password"),
    role_ids: data.getAll("role_ids"), mfa_required: data.get("mfa_required") === "on",
  }).then(() => undefined)}><label>Username<input name="username" required pattern="[A-Za-z0-9._-]{2,128}" /></label><label>Display name<input name="display_name" required /></label><label>Initial password<input name="password" type="password" minLength={12} required /></label><fieldset><legend>Roles</legend>{roles.map((role) => <label key={role.id}><input type="checkbox" name="role_ids" value={role.id} />{role.name}</label>)}</fieldset><label><input name="mfa_required" type="checkbox" /> Require MFA enrollment</label></MutationForm>;
}

export function UserStateForm({ id, active }: { id: string; active: boolean }) {
  return <MutationForm label={active ? "Deactivate" : "Activate"} onSubmit={() => mutate("site", `/api/v1/admin/security/users/${id}/${active ? "deactivate" : "activate"}`, "POST", {}).then(() => undefined)}><span /></MutationForm>;
}

export function RoleCreateForm({ permissions }: { permissions: Array<{ code: string; description?: string }> }) {
  return <MutationForm label="Create role" onSubmit={(data) => mutate("site", "/api/v1/admin/security/roles", "POST", {
    name: data.get("name"), description: data.get("description") || null, permission_codes: data.getAll("permission_codes"),
  }).then(() => undefined)}><label>Role name<input name="name" required minLength={2} /></label><label>Description<input name="description" /></label><fieldset><legend>Permissions</legend>{permissions.map((permission) => <label key={permission.code}><input type="checkbox" name="permission_codes" value={permission.code} />{permission.code}</label>)}</fieldset></MutationForm>;
}

export function DlqReplayForm({ id }: { id: string }) {
  return <MutationForm label="Replay" onSubmit={() => mutate("site", `/api/v1/admin/system/dlq/${id}/replay`, "POST", {}).then(() => undefined)}><span /></MutationForm>;
}
