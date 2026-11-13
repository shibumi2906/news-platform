"use client";

import { useState } from "react";
import { MutationForm, mutate } from "./forms";
import { Help, PreviewResults, type PreviewResult } from "./topics";

export interface ModelSettings {
  model: string;
  canary: string | null;
  changed_at: string | null;
  changed_by: string | null;
  can_rollback: boolean;
  options: Array<{ model: string; input: number; output: number }>;
}

const modelPath = "/api/v1/ai/relevance/model";
const previewPath = "/api/v1/ai/relevance/preview";

export function ModelEditor({ settings }: { settings: ModelSettings }) {
  const [results, setResults] = useState<PreviewResult[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function compare(form: HTMLFormElement) {
    const data = new FormData(form);
    const text = String(data.get("sample") ?? "").trim();
    setError("");
    setResults([]);
    if (!text) { setError("Enter a sample headline or article."); return; }
    setBusy(true);
    try {
      const current = await mutate("integrator", previewPath, "POST", { text });
      const candidate = await mutate("integrator", previewPath, "POST", { text, model: data.get("model") });
      setResults([current, candidate]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Model comparison failed.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="admin-panel">
    <h2>Selection model</h2>
    <p>Current model: <strong>{settings.model}</strong></p>
    {settings.canary && <p>Model in limited rollout: {settings.canary}</p>}
    {settings.changed_at && <p>Changed {settings.changed_at.slice(0, 10)}{settings.changed_by && ` by ${settings.changed_by}`}</p>}
    {settings.options.length ? <MutationForm label="Apply to new materials" resetOnSuccess={false} onSubmit={async (data) => {
      await mutate("integrator", modelPath, "PUT", { model: data.get("model") });
    }}>
      <label>Model<select name="model" defaultValue={settings.model}>
        {settings.options.map((option) => <option key={option.model} value={option.model}>
          {option.model}{(option.input || option.output) ? ` · $${option.input} input / $${option.output} output per 1M tokens` : ""}
        </option>)}
      </select></label>
      <Help>This model decides which topics match new materials. Prices are per million tokens.</Help>
      <label>Sample headline or article<textarea name="sample" maxLength={16000} /></label>
      <Help>Compare both models on the same sample and active topics. Tests use the AI provider and stay out of the materials feed.</Help>
      <button type="button" disabled={busy} onClick={(event) => { if (event.currentTarget.form) void compare(event.currentTarget.form); }}>{busy ? "Comparing…" : "Compare models"}</button>
      {error && <p role="alert" className="form-error">{error}</p>}
      <PreviewResults results={results} />
    </MutationForm> : <p>Configure the OpenAI API key on the server to choose an OpenAI model.</p>}
    {settings.can_rollback && <MutationForm label="Restore previous model" onSubmit={async () => {
      await mutate("integrator", `${modelPath}/rollback`, "POST", {});
    }}>{null}</MutationForm>}
  </section>;
}
