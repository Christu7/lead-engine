export interface Lead {
  id: number;
  client_id: number;
  name: string;
  email: string;
  phone: string | null;
  company: string | null;
  title: string | null;
  source: string | null;
  status: string;
  score: number | null;
  enrichment_data: Record<string, unknown> | null;
  enrichment_status: string;
  score_details: Record<string, unknown> | null;
  ai_analysis: AIAnalysis | null;
  ai_analyzed_at: string | null;
  ai_status: "analyzing" | "completed" | "failed" | null;
  created_at: string;
  updated_at: string;
}

export interface AIQualification {
  rating: "hot" | "warm" | "cold";
  reasoning: string;
}

export interface AIAnalysis {
  company_summary: string;
  icebreakers: string[];
  qualification: AIQualification;
  email_angle: string;
}

export interface EnrichmentLog {
  id: number;
  provider: string;
  raw_response: Record<string, unknown> | null;
  success: boolean;
  created_at: string;
}

export interface RoutingLog {
  id: number;
  destination: string;
  payload: Record<string, unknown> | null;
  response_code: number | null;
  success: boolean;
  error: string | null;
  created_at: string;
}

export interface LeadDetail extends Lead {
  enrichment_logs: EnrichmentLog[];
  routing_logs: RoutingLog[];
}

export interface LeadListResponse {
  items: Lead[];
  total: number;
  limit: number;
  offset: number;
}

// ── Export types ──────────────────────────────────────────────────────────────

export interface LeadFiltersExport {
  source?: string;
  status?: string;
  score_min?: number;
  score_max?: number;
  date_from?: string;
  date_to?: string;
  search?: string;
}

export interface WebhookExportRequest {
  webhook_url: string;
  filters?: LeadFiltersExport;
  batch_size?: number;
  include_enrichment?: boolean;
  include_ai_analysis?: boolean;
}

export interface WebhookExportResponse {
  export_id: string;
  total_leads: number;
  total_batches: number;
  status: string;
  webhook_url: string;
}
