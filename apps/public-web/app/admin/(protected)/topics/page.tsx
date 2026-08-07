import { TopicCreateForm } from "@/components/admin/forms";
import { getAdminIntegrator } from "@/lib/api";

interface Topic { id: string; name: string; slug: string; description: string | null; categories: Array<{ name: string; slug: string; parent_slug?: string | null }>; keywords: string[]; priority: number; relevance_threshold: number; is_active: boolean; }

export default async function TopicsPage() {
  const topics = await getAdminIntegrator<Topic[]>("/api/v1/ai/topics");
  return <><header className="admin-heading"><div><p className="kicker">AI policy</p><h1>Topics & categories</h1></div><span>Database managed</span></header><div className="admin-two-column"><section className="admin-panel"><h2>Relevance map</h2><div className="admin-list">{topics.map((topic) => <article key={topic.id}><div><strong>{topic.name}</strong><p>{topic.description || topic.slug}</p><div className="chip-row">{topic.categories.map((category) => <span key={category.slug}>{category.name}</span>)}</div></div><div><span className={`status ${topic.is_active ? "status-active" : "status-disabled"}`}>{topic.is_active ? "active" : "disabled"}</span><small>priority {topic.priority} · ≥ {topic.relevance_threshold}</small></div></article>)}</div></section><aside className="admin-panel"><h2>Create topic</h2><TopicCreateForm /></aside></div></>;
}
