export interface LeadsBySource {
  source: string;
  count: number;
}

export interface ScoreBucket {
  label: string;
  count: number;
}

export interface RoutingBreakdownItem {
  destination: string;
  total: number;
  success: number;
  failed: number;
}

export interface ActivityItem {
  type: string;
  lead_id: number;
  lead_name: string;
  description: string;
  timestamp: string;
}

export interface DashboardStats {
  total_leads: number;
  leads_this_week: number;
  leads_this_month: number;
  enrichment_success_rate: number;
  average_score: number | null;
  leads_by_source: LeadsBySource[];
  score_distribution: ScoreBucket[];
  routing_breakdown: RoutingBreakdownItem[];
  recent_activity: ActivityItem[];
}
