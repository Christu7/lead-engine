import { apiFetch } from "./client";
import type { ScoringRule, ScoringRuleListResponse, ScoringTemplate } from "../types/scoring";

export async function fetchScoringRules(): Promise<ScoringRuleListResponse> {
  const res = await apiFetch("/scoring-rules/");
  if (!res.ok) throw new Error("Failed to fetch scoring rules");
  return res.json();
}

export async function fetchTemplates(): Promise<ScoringTemplate[]> {
  const res = await apiFetch("/scoring-rules/templates");
  if (!res.ok) throw new Error("Failed to fetch templates");
  return res.json();
}

export async function createScoringRule(data: {
  field: string;
  operator: string;
  value: string;
  points: number;
  is_active: boolean;
}): Promise<ScoringRule> {
  const res = await apiFetch("/scoring-rules/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create scoring rule");
  return res.json();
}

export async function updateScoringRule(
  id: number,
  data: Partial<{ field: string; operator: string; value: string; points: number; is_active: boolean }>
): Promise<ScoringRule> {
  const res = await apiFetch(`/scoring-rules/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update scoring rule");
  return res.json();
}

export async function deleteScoringRule(id: number): Promise<void> {
  const res = await apiFetch(`/scoring-rules/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete scoring rule");
}

export async function applyTemplate(name: string): Promise<ScoringRule[]> {
  const res = await apiFetch(`/scoring-rules/templates/${name}/apply`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to apply template");
  return res.json();
}
