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
  created_at: string;
  updated_at: string;
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
