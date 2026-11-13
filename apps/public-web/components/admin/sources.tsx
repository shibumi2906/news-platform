"use client";

import { useState } from "react";
import { MutationForm, mutate } from "./forms";
import { Help, PreviewResults, type PreviewResult } from "./topics";

export interface Source {
  id: string;
  name: string;
  feed_url: string;
  adapter_type: string;
  poll_interval_seconds: number;
  is_active: boolean;
  health_status: string;
  health_reason: string | null;
  last_success_at: string | null;
}

interface Sample { title: string; url: string; text: string }
const path = "/api/v1/sources";

export function SourcesEditor({ sources }: { sources: Source[] }) {
  const [editor, setEditor] = useState<Source | "add">();
  return <>
    <button onClick={() => setEditor("add")}>Add source</button>
    <div className="admin-two-column settings-columns">
      <section className="admin-panel">
        <h2>Configured sources</h2>
        {!sources.length && <p>No sources configured.</p>}
        <div className="admin-list">{sources.map((source) => <article key={source.id}>
          <div><strong>{source.name}</strong><p>{source.adapter_type} · {source.is_active ? "Active" : "Paused"} · {source.health_status}</p>
            <p>{source.feed_url}</p>
            <small>Last successful collection: {source.last_success_at ? new Date(source.last_success_at).toLocaleString() : "None yet"}</small>
            {source.health_reason && <p className="form-error">{source.health_reason}</p>}
          </div>
          <div className="row-actions">
            <button onClick={() => setEditor(source)}>Edit</button>
            <MutationForm label={source.is_active ? "Pause" : "Activate"} onSubmit={async () => {
              await mutate("integrator", `${path}/${source.id}/${source.is_active ? "deactivate" : "activate"}`, "POST", {});
            }}>{null}</MutationForm>
          </div>
        </article>)}</div>
      </section>
      {editor && <section className="admin-panel">
        <h2>{editor === "add" ? "Add source" : "Edit source"}</h2>
        <SourceForm key={editor === "add" ? editor : editor.id} source={editor === "add" ? undefined : editor} close={() => setEditor(undefined)} />
      </section>}
    </div>
  </>;
}

function SourceForm({ source, close }: { source?: Source; close: () => void }) {
  const [adapter, setAdapter] = useState(source?.adapter_type ?? "rss");
  const [samples, setSamples] = useState<Sample[]>();
  const [results, setResults] = useState<PreviewResult[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const payload = (data: FormData) => ({
    name: String(data.get("name") || "Preview"),
    feed_url: data.get("url"),
    adapter_type: adapter,
    poll_interval_seconds: source?.poll_interval_seconds ?? 300,
  });

  async function check(form: HTMLFormElement) {
    setSamples(undefined);
    setResults([]);
    setError("");
    setBusy(true);
    try {
      const data = new FormData(form);
      if (!data.get("url")) throw new Error("Enter a source URL.");
      const result = await mutate("integrator", `${path}/sample`, "POST", payload(data)) as { items: Sample[] };
      setSamples(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not check this source.");
    } finally {
      setBusy(false);
    }
  }

  async function test(sample: Sample) {
    setError("");
    setResults([]);
    setBusy(true);
    try {
      setResults([await mutate("integrator", "/api/v1/ai/relevance/preview", "POST", {
        text: `${sample.title}\n${sample.text}`.slice(0, 16000),
      })]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Selection test failed.");
    } finally {
      setBusy(false);
    }
  }

  return <MutationForm label={source ? "Save changes" : "Add source"} onSubmit={async (data) => {
    await mutate("integrator", source ? `${path}/${source.id}` : path, source ? "PUT" : "POST", payload(data));
    close();
  }}>
    <label>Name<input name="name" defaultValue={source?.name} maxLength={255} required /></label>
    <Help>A recognizable label, such as Film festival news.</Help>
    <label>Type<select value={adapter} onChange={(event) => { setAdapter(event.target.value); setSamples(undefined); setResults([]); }}>
      <option value="rss">RSS / Atom</option><option value="youtube">YouTube</option>
      {source && !["rss", "youtube"].includes(source.adapter_type) && <option value={source.adapter_type}>{source.adapter_type}</option>}
    </select></label>
    <Help>RSS and Atom read a feed. YouTube collects video titles and descriptions from a channel or playlist.</Help>
    <label>Source URL<input name="url" type="url" defaultValue={source?.feed_url} onChange={() => { setSamples(undefined); setResults([]); }} required /></label>
    <Help>{adapter === "youtube" ? "Paste a channel URL such as youtube.com/@channel or a YouTube playlist URL. The API key is configured on the server." : "Paste the direct feed address, for example https://example.org/culture/feed.xml."}</Help>
    <div className="row-actions">
      {["rss", "youtube"].includes(adapter) && <button type="button" disabled={busy} onClick={(event) => { if (event.currentTarget.form) void check(event.currentTarget.form); }}>Check source</button>}
      <button type="button" onClick={close}>Cancel</button>
    </div>
    {busy && <p role="status">Checking…</p>}
    {error && <p role="alert" className="form-error">{error === "missing_youtube_api_key" ? "The server needs a YouTube API key." : error}</p>}
    {samples && (samples.length ? <ul>{samples.map((sample, index) => <li key={index}>
      {sample.title} <button type="button" disabled={busy} onClick={() => void test(sample)}>Test selection</button>
    </li>)}</ul> : <p>No usable items found. Check that the URL points to a feed, channel, or playlist with public items.</p>)}
    <PreviewResults results={results} />
  </MutationForm>;
}
