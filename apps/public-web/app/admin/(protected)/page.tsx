import Link from "next/link";
import { getAdminArticles, getAdminIntegrator } from "@/lib/api";

interface AIRun { status: string; estimated_cost_usd: number; }

export default async function AdminOverview() {
  const [articles, runs] = await Promise.all([getAdminArticles(), getAdminIntegrator<AIRun[]>("/api/v1/admin/ai-runs?limit=100")]);
  const failures = runs.filter((run) => run.status === "failed").length;
  const cost = runs.reduce((sum, run) => sum + run.estimated_cost_usd, 0);
  return <><header className="admin-heading"><div><p className="kicker">Operational snapshot</p><h1>Overview</h1></div><span>API-backed · live</span></header><div className="metric-grid"><article><span>Articles</span><strong>{articles.length}</strong></article><article><span>Awaiting review</span><strong>{articles.filter((item) => item.status === "needs_review").length}</strong></article><article><span>AI failures</span><strong>{failures}</strong></article><article><span>Estimated AI cost</span><strong>${cost.toFixed(4)}</strong></article></div><section className="admin-panel"><h2>Next actions</h2><div className="quick-links"><Link href="/admin/incoming">Triage incoming packages</Link><Link href="/admin/articles">Open editorial queue</Link><Link href="/admin/telemetry">Inspect AI operations</Link></div></section></>;
}
