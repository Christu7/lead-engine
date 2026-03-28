import type { CustomFieldValues } from "./custom_field";

export interface Company {
  id: string;
  client_id: number;
  name: string;
  domain: string | null;
  website: string | null;
  industry: string | null;
  employee_count: number | null;
  location_city: string | null;
  location_state: string | null;
  location_country: string | null;
  apollo_id: string | null;
  funding_stage: string | null;
  annual_revenue_range: string | null;
  tech_stack: string[] | null;
  keywords: string[] | null;
  linkedin_url: string | null;
  founded_year: number | null;
  enrichment_status: "pending" | "enriching" | "enriched" | "partial" | "failed";
  enriched_at: string | null;
  abm_status: "target" | "active" | "inactive";
  lead_count: number;
  created_at: string;
  updated_at: string;
  custom_fields: CustomFieldValues;
}

export interface CompanyDetail extends Company {
  leads: LeadSummary[];
}

export interface LeadSummary {
  id: number;
  name: string;
  email: string;
  title: string | null;
  score: number | null;
  enrichment_status: string;
}

export interface ContactPullRequest {
  titles: string[];
  seniorities: string[];
  limit: number;
}

export interface CompanyBulkUploadResponse {
  created: number;
  updated: number;
  skipped: number;
  errors: string[];
}
