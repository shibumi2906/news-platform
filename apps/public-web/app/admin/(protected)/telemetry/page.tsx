import { getAdminIntegrator } from "@/lib/api";

interface Run { id: string; operation: string; provider: string; model: string; status: string; error_code: string | null; prompt_tokens: number; completion_tokens: number; latency_ms: number; estimated_cost_usd: number; created_at: string; }

export default async function TelemetryPage() {
  const runs = await getAdminIntegrator<Run[]>("/api/v1/admin/ai-runs?limit=200");
  return <><header className="admin-heading"><div><p className="kicker">Safe observability</p><h1>AI telemetry</h1></div><span>No prompts or outputs exposed</span></header><section className="admin-panel table-scroll"><table><caption className="visually-hidden">AI operation telemetry and errors</caption><thead><tr><th>Operation</th><th>Provider / model</th><th>Status</th><th>Tokens</th><th>Latency</th><th>Cost</th><th>Error</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id}><td>{run.operation}</td><td>{run.provider} / {run.model}</td><td><span className={`status status-${run.status}`}>{run.status}</span></td><td>{run.prompt_tokens + run.completion_tokens}</td><td>{run.latency_ms} ms</td><td>${run.estimated_cost_usd.toFixed(5)}</td><td>{run.error_code || "—"}</td></tr>)}</tbody></table></section></>;
}
