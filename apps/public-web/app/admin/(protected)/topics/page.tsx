import { TopicsEditor, type TopicSettings } from "@/components/admin/topics";
import { getAdminIntegrator } from "@/lib/api";

export default async function TopicsPage() {
  const topics = await getAdminIntegrator<TopicSettings[]>("/api/v1/ai/topics");
  return <><header className="admin-heading"><h1>Topics & categories</h1></header><TopicsEditor topics={topics} /></>;
}
