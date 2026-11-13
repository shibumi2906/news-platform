"use client";

import { MutationForm, mutate } from "./forms";

export function SiteDeliveryMode({ id, mode }: { id: string; mode: string }) {
  return <MutationForm label="Save delivery mode" resetOnSuccess={false} onSubmit={async (data) => {
    await mutate("integrator", `/api/v1/admin/site-feed-activity/${id}`, "PUT", { mode: data.get("mode") });
  }}>
    <label>Delivery mode<select name="mode" defaultValue={mode}>
      <option value="push">Send to site</option>
      <option value="pull">Site requests materials</option>
    </select></label>
  </MutationForm>;
}
