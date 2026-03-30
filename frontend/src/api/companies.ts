import { apiFetch } from "./client";
import type { Company, CompanyBulkUploadResponse, CompanyDetail, ContactPullRequest } from "../types/company";

export interface CompanyFilters {
  skip?: number;
  limit?: number;
  enrichment_status?: string;
  abm_status?: string;
  industry?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}

export async function getCompanies(
  params: CompanyFilters = {},
): Promise<{ items: Company[]; total: number }> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "" && value !== null) {
      qs.set(key, String(value));
    }
  }
  const res = await apiFetch(`/companies/?${qs.toString()}`);
  if (!res.ok) throw new Error("Failed to fetch companies");
  return res.json();
}

export async function getCompany(id: string): Promise<CompanyDetail> {
  const res = await apiFetch(`/companies/${id}`);
  if (!res.ok) throw new Error("Failed to fetch company");
  return res.json();
}

export async function createCompany(data: Partial<Company>): Promise<Company> {
  const res = await apiFetch("/companies/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (res.status === 409) throw new Error("A company with that domain already exists");
  if (!res.ok) throw new Error("Failed to create company");
  return res.json();
}

export async function updateCompany(id: string, data: Partial<Company>): Promise<Company> {
  const res = await apiFetch(`/companies/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update company");
  return res.json();
}

export async function deleteCompany(id: string): Promise<void> {
  const res = await apiFetch(`/companies/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete company");
}

export async function enrichCompany(id: string): Promise<void> {
  const res = await apiFetch(`/companies/${id}/enrich`, { method: "POST" });
  if (res.status === 409) throw new Error("Enrichment already in progress");
  if (!res.ok) throw new Error("Failed to start enrichment");
}

export async function pullContacts(id: string, filters: ContactPullRequest): Promise<void> {
  const res = await apiFetch(`/companies/${id}/pull-contacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filters),
  });
  if (res.status === 400) throw new Error("Company must be enriched before pulling contacts");
  if (!res.ok) throw new Error("Failed to start contact pull");
}

export async function bulkEnrichCompanies(): Promise<{ queued: number }> {
  const res = await apiFetch("/companies/bulk-enrich", { method: "POST" });
  if (!res.ok) throw new Error("Failed to start bulk enrichment");
  return res.json();
}

export async function uploadCompaniesCsv(
  file: File,
  columnMapping?: Record<string, string>,
): Promise<CompanyBulkUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (columnMapping) {
    form.append("column_mapping", JSON.stringify(columnMapping));
  }
  const res = await apiFetch("/companies/bulk", {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error("Failed to upload CSV");
  return res.json();
}
