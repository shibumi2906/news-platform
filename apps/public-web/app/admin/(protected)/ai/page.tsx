import { ModelEditor, type ModelSettings } from "@/components/admin/models";
import { getAdminIntegrator } from "@/lib/api";

export default async function AISettingsPage() {
  const settings = await getAdminIntegrator<ModelSettings>("/api/v1/ai/relevance/model");
  return <><header className="admin-heading"><h1>AI settings</h1></header><ModelEditor settings={settings} /></>;
}
