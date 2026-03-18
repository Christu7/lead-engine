import { apiFetch } from "./client";
import type { LeadDetail, LeadListResponse } from "../types/lead";

export interface LeadFilters {
  limit?: number;
  offset?: number;
  source?: string;
  status?: string;
  score_min?: number;
  score_max?: number;
  search?: string;
  created_after?: string;
  created_before?: string;
  sort_by?: string;
  sort_order?: string;
}

export async function fetchLeads(filters: LeadFilters): Promise<LeadListResponse> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "" && value !== null) {
      params.set(key, String(value));
    }
  }
  const res = await apiFetch(`/leads/?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to fetch leads");
  return res.json();
}

export async function fetchLeadDetail(leadId: number): Promise<LeadDetail> {
  const res = await apiFetch(`/leads/${leadId}/detail`);
  if (!res.ok) throw new Error("Failed to fetch lead detail");
  return res.json();
}

export async function enrichLead(leadId: number): Promise<void> {
  const res = await apiFetch(`/leads/${leadId}/enrich`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to enrich lead");
}

export async function routeLead(leadId: number): Promise<void> {
  const res = await apiFetch(`/leads/${leadId}/route`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to route lead");
}

export async function runAiAnalysis(leadId: number): Promise<void> {
  const res = await apiFetch(`/leads/${leadId}/ai-analyze`, { method: "POST" });
  if (res.status === 409) throw new Error("Analysis already in progress");
  if (!res.ok) throw new Error("Failed to start AI analysis");
}
