import Link from "next/link";
import { getAdminArticles } from "@/lib/api";

export default async function ArticlesPage() {
  const articles = await getAdminArticles();
  return <><header className="admin-heading"><div><p className="kicker">Editorial</p><h1>Articles</h1></div><span>{articles.length} records</span></header><section className="admin-panel"><div className="admin-list">{articles.map((article) => <article key={article.id}><div><strong><Link href={`/admin/articles/${article.id}`}>{article.id}</Link></strong><p>Version {article.latest_version_number} · lock {article.lock_version}</p><small>Updated {new Date(article.updated_at).toLocaleString()}</small></div><span className={`status status-${article.status}`}>{article.status.replaceAll("_", " ")}</span></article>)}</div></section></>;
}
