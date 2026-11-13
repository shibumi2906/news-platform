import { SourcesEditor, type Source } from "@/components/admin/sources";
import { getAdminIntegrator } from "@/lib/api";

export default async function SourcesPage() {
  const sources = await getAdminIntegrator<Source[]>("/api/v1/sources");
  return <><header className="admin-heading"><h1>Sources</h1></header><SourcesEditor sources={sources} /></>;
}
