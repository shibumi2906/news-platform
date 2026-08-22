import { getAdminSite } from "@/lib/api";
interface Campaign { id: string; status: string | null; }
export default async function AdvertisingPage() { const campaigns = await getAdminSite<Campaign[]>("/api/v1/admin/advertising/campaigns"); return <><header className="admin-heading"><div><p className="kicker">Commercial</p><h1>Advertising</h1></div><span>{campaigns.length} campaigns</span></header><section className="admin-panel">{campaigns.length ? campaigns.map((x) => <p key={x.id}>{x.id.slice(0, 8)} · {x.status}</p>) : <p>No campaigns yet.</p>}</section></>; }
