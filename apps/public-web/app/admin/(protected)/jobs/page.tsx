import { DlqReplayForm } from "@/components/admin/forms";
import { getAdminSite } from "@/lib/api";

interface Job { id: string; queue: string; kind: string; status: string; attempt_count: number; max_attempts: number; error_code?: string }
interface Letter { id: string; job_id: string; queue: string; kind: string; reason_code: string; replay_count: number }

export default async function JobsPage() {
  const [jobs, letters] = await Promise.all([
    getAdminSite<Job[]>("/api/v1/admin/system/jobs"),
    getAdminSite<Letter[]>("/api/v1/admin/system/dlq"),
  ]);
  return <><header className="admin-heading"><div><p className="kicker">Reliability control plane</p><h1>Jobs & DLQ</h1></div></header>{letters.length > 0 && <section className="admin-panel"><h2>Dead letters</h2>{letters.map((letter) => <article key={letter.id}><strong>{letter.kind}</strong><p>{letter.reason_code} · replayed {letter.replay_count} times</p><DlqReplayForm id={letter.id} /></article>)}</section>}<section className="admin-panel"><h2>Recent jobs</h2><div className="table-wrap"><table><thead><tr><th>Queue / kind</th><th>Status</th><th>Attempts</th><th>Error</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td>{job.queue}<br /><small>{job.kind}</small></td><td>{job.status}</td><td>{job.attempt_count}/{job.max_attempts}</td><td>{job.error_code ?? "—"}</td></tr>)}</tbody></table></div></section></>;
}
