import { apiFetch } from "./client";
import type { RoutingSettings, EnrichmentSettings } from "../types/settings";

export async function fetchRoutingSettings(): Promise<RoutingSettings> {
  const res = await apiFetch("/settings/routing");
  if (!res.ok) throw new Error("Failed to fetch routing settings");
  return res.json();
}

export async function updateRoutingSettings(data: RoutingSettings): Promise<RoutingSettings> {
  const res = await apiFetch("/settings/routing", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update routing settings");
  return res.json();
}

export async function fetchEnrichmentSettings(): Promise<EnrichmentSettings> {
  const res = await apiFetch("/settings/enrichment");
  if (!res.ok) throw new Error("Failed to fetch enrichment settings");
  return res.json();
}

export async function updateEnrichmentSettings(
  data: Partial<EnrichmentSettings>
): Promise<EnrichmentSettings> {
  const res = await apiFetch("/settings/enrichment", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update enrichment settings");
  return res.json();
}
