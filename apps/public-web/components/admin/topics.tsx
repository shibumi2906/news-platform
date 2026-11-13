"use client";

import { useState } from "react";
import { MutationForm, mutate } from "./forms";

export interface TopicSettings {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  categories: Array<{ name: string; slug: string; parent_slug?: string | null; keywords: string[] }>;
  keywords: string[];
  exclusions: string[];
  regions: string[];
  priority: number;
  relevance_threshold: number;
  additional_rules: Record<string, unknown>;
  is_active: boolean;
}

export function Help({ children }: { children: React.ReactNode }) {
  return <details className="setting-help"><summary aria-label="Help">?</summary><small>{children}</small></details>;
}

function words(value: FormDataEntryValue | null) {
  return String(value ?? "").split(",").map((term) => term.trim()).filter(Boolean);
}

function slug(name: string, fallback: string) {
  return name.normalize("NFKD").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 180).replace(/-$/, "") || fallback;
}

export interface PreviewResult {
  model: string;
  estimated_cost_usd: number;
  matches: Array<{ topic_id: string; topic: string; is_relevant: boolean; category_slug: string | null; reason: Record<string, unknown> }>;
}

export function Reason({ value }: { value: Record<string, unknown> }) {
  return <>{Object.values(value).flat().filter((item): item is string => typeof item === "string").join(" · ")}</>;
}

export function PreviewResults({ results }: { results: PreviewResult[] }) {
  return <div aria-live="polite">{results.map((result, index) => (
    <section key={index} className="selection-result">
      <strong>{result.model}</strong> · ${result.estimated_cost_usd.toFixed(5)}
      {result.matches.length ? <ul>{result.matches.map((match) => <li key={match.topic_id}>
        {match.topic} · {match.is_relevant ? "Matched" : "Rejected"}
        {match.category_slug && <> · {match.category_slug}</>} · <Reason value={match.reason} />
      </li>)}</ul> : <p>No topic decisions returned.</p>}
    </section>
  ))}</div>;
}

type Editor = { mode: "add" | "edit" | "copy"; topic?: TopicSettings };
const topicPath = "/api/v1/ai/topics";

export function TopicsEditor({ topics }: { topics: TopicSettings[] }) {
  const [editor, setEditor] = useState<Editor>();
  return <>
    <button onClick={() => setEditor({ mode: "add" })}>Add topic</button>
    <div className="admin-two-column settings-columns">
      <section className="admin-panel">
        <h2>Relevance map</h2>
        {!topics.length && <p>No topics configured.</p>}
        <div className="admin-list">{topics.map((topic) => <article key={topic.id}>
          <div><strong>{topic.name}</strong><p>{topic.description}</p>
            <div className="chip-row">{topic.categories.map((category) => <span key={category.slug}>{category.name}</span>)}</div>
            <small>{topic.regions.join(", ") || "Worldwide"} · {topic.is_active ? "Active" : "Paused"}</small>
            <details><summary>Site feed topic ID</summary><code>{topic.slug}</code></details>
          </div>
          <div className="row-actions">
            <button aria-label={`Edit ${topic.name}`} onClick={() => setEditor({ mode: "edit", topic })}>Edit</button>
            <button aria-label={`Copy ${topic.name}`} onClick={() => setEditor({ mode: "copy", topic })}>Copy</button>
          </div>
        </article>)}</div>
      </section>
      {editor && <section className="admin-panel">
        <h2>{editor.mode === "edit" ? "Edit topic" : editor.mode === "copy" ? "Copy topic" : "Add topic"}</h2>
        <TopicForm key={`${editor.mode}:${editor.topic?.id ?? ""}`} editor={editor} close={() => setEditor(undefined)} />
      </section>}
    </div>
  </>;
}

function TopicForm({ editor, close }: { editor: Editor; close: () => void }) {
  const { topic, mode } = editor;
  const [categories, setCategories] = useState(() => (topic?.categories ?? []).map((row, index) => ({ ...row, key: String(index) })));
  const [results, setResults] = useState<PreviewResult[]>([]);
  const [previewError, setPreviewError] = useState("");
  const [testing, setTesting] = useState(false);

  function settings(data: FormData) {
    const name = String(data.get("name") ?? "").trim();
    if (!name) throw new Error("Enter a topic name.");
    const usedSlugs = new Set(categories.map((category) => category.slug).filter(Boolean));
    const updated = categories.map((category) => {
      const label = category.name.trim();
      if (!label) throw new Error("Enter a name for each category.");
      let key = category.slug;
      if (!key) {
        const base = slug(label, "category");
        key = base;
        for (let suffix = 2; usedSlugs.has(key); suffix++) key = `${base}-${suffix}`;
        usedSlugs.add(key);
      }
      return { name: label, slug: key, keywords: category.keywords, parent_slug: usedSlugs.has(category.parent_slug ?? "") ? category.parent_slug : null };
    });
    const include = String(data.get("include") ?? "").trim();
    const exclude = String(data.get("exclude") ?? "").trim();
    const legacyExclusions = topic?.exclusions.join(", ") ?? "";
    return {
      name,
      slug: mode === "edit" ? topic?.slug : `${slug(name, "topic")}-${crypto.randomUUID().slice(0, 8)}`,
      description: include || null,
      categories: updated,
      keywords: words(data.get("keywords")),
      exclusions: exclude === legacyExclusions && !topic?.additional_rules.exclude_criteria ? topic?.exclusions ?? [] : [],
      regions: words(data.get("regions")),
      priority: topic?.priority ?? 0,
      relevance_threshold: topic?.relevance_threshold ?? 0.5,
      additional_rules: {
        ...topic?.additional_rules,
        include_criteria: include,
        exclude_criteria: exclude,
      },
      is_active: data.has("active"),
    };
  }

  async function test(form: HTMLFormElement) {
    const data = new FormData(form);
    setPreviewError("");
    setResults([]);
    setTesting(true);
    try {
      const text = String(data.get("sample") ?? "").trim();
      if (!text) throw new Error("Paste a headline or article to test.");
      setResults([await mutate("integrator", "/api/v1/ai/relevance/preview", "POST", {
        text, topic: settings(data), topic_id: mode === "edit" ? topic?.id : undefined,
      })]);
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Preview failed.");
    } finally {
      setTesting(false);
    }
  }

  return <MutationForm label={mode === "edit" ? "Save changes" : "Create topic"} onSubmit={async (data) => {
    await mutate("integrator", mode === "edit" ? `${topicPath}/${topic?.id}` : topicPath, mode === "edit" ? "PUT" : "POST", settings(data));
    close();
  }}>
    <label>Name<input name="name" maxLength={255} defaultValue={mode === "copy" ? `${topic?.name} copy` : topic?.name} required /></label>
    <Help>The label shown in the topic list. A copy can have a new name, such as Texas news.</Help>
    <label>What to select<textarea name="include" maxLength={2000} defaultValue={String(topic?.additional_rules.include_criteria ?? topic?.description ?? "")} /></label>
    <Help>Describe subjects the model should accept. Example: film premieres, art exhibitions and video game releases. Leave blank to use the other criteria.</Help>
    <label>What to exclude<textarea name="exclude" maxLength={2000} defaultValue={String(topic?.additional_rules.exclude_criteria || topic?.exclusions.join(", ") || "")} /></label>
    <Help>Describe main subjects to reject. Example: reject coverage of armed conflicts. A film premiere about a war can still qualify.</Help>
    <label>Regions<input name="regions" defaultValue={topic?.regions.join(", ")} /></label>
    <Help>Enter event locations separated by commas, such as Texas, California. Leave blank for worldwide coverage.</Help>
    <label>Keywords<input name="keywords" defaultValue={topic?.keywords.join(", ")} /></label>
    <Help>Optional cues separated by commas, such as premiere, exhibition, runway. Add terms in the languages of your sources.</Help>
    <fieldset className="topic-categories"><legend>Categories</legend>
      <Help>Categories organize accepted stories. Leave the list empty if you only need the topic label.</Help>
      {categories.map((category) => <div className="category-fields" key={category.key}>
        <label>Category name<input value={category.name} required onChange={(event) => setCategories(categories.map((item) => item.key === category.key ? { ...item, name: event.target.value } : item))} /></label>
        <label>Category keywords<input defaultValue={category.keywords.join(", ")} onChange={(event) => setCategories(categories.map((item) => item.key === category.key ? { ...item, keywords: words(event.target.value) } : item))} /></label>
        <Help>Give the category a reader-facing name. Keywords are optional hints for assigning stories to it.</Help>
        <button type="button" onClick={() => setCategories(categories.filter((item) => item.key !== category.key))}>Remove category</button>
      </div>)}
      <button type="button" onClick={() => setCategories([...categories, { name: "", slug: "", keywords: [], key: crypto.randomUUID() }])}>Add category</button>
    </fieldset>
    <label className="checkbox-label"><input type="checkbox" name="active" defaultChecked={topic?.is_active ?? true} /> Active</label>
    <Help>Active topics are used to select new materials. Pause a topic to keep its settings for later.</Help>
    <label>Sample headline or article<textarea name="sample" maxLength={16000} /></label>
    <Help>Tests the rules shown here before you save. The sample stays out of the materials feed.</Help>
    <div className="row-actions">
      <button type="button" disabled={testing} onClick={(event) => { if (event.currentTarget.form) void test(event.currentTarget.form); }}>{testing ? "Checking…" : "Test selection"}</button>
      <button type="button" onClick={close}>Cancel</button>
    </div>
    {previewError && <p role="alert" className="form-error">{previewError}</p>}
    <PreviewResults results={results} />
  </MutationForm>;
}
