import { apiFetch } from "./client";
import type { ApiKeyEntry, EnrichmentSettings, RoutingSettings } from "../types/settings";

// ── Routing ───────────────────────────────────────────────────────────────────

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

// ── Enrichment ────────────────────────────────────────────────────────────────

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

// ── API Key Store ──────────────────────────────────────────────────────────────

export interface SetKeyResult extends ApiKeyEntry {
  verified: boolean;
}

export async function getApiKeys(): Promise<ApiKeyEntry[]> {
  const res = await apiFetch("/settings/keys");
  if (!res.ok) throw new Error("Failed to fetch API keys");
  return res.json();
}

export async function setApiKey(keyName: string, value: string): Promise<SetKeyResult> {
  const res = await apiFetch(`/settings/keys/${keyName}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  if (!res.ok) throw new Error("Failed to save API key");
  return res.json();
}

export async function deleteApiKey(keyName: string): Promise<void> {
  const res = await apiFetch(`/settings/keys/${keyName}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete API key");
}

export async function verifyApiKey(
  keyName: string
): Promise<{ verified: boolean; last_verified_at: string | null }> {
  const res = await apiFetch(`/settings/keys/${keyName}/verify`, { method: "POST" });
  if (!res.ok) throw new Error("Verification failed");
  return res.json();
}

// ── AI Provider ────────────────────────────────────────────────────────────────

export async function getAiProvider(): Promise<{ provider: string; available: string[] }> {
  const res = await apiFetch("/settings/ai-provider");
  if (!res.ok) throw new Error("Failed to fetch AI provider");
  return res.json();
}

export async function setAiProvider(provider: string): Promise<void> {
  const res = await apiFetch("/settings/ai-provider", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
  if (res.status === 400) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to set AI provider");
  }
  if (!res.ok) throw new Error("Failed to set AI provider");
}
