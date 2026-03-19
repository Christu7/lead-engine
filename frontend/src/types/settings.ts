export interface RoutingSettings {
  ghl_inbound_webhook_url: string | null;
  ghl_outbound_webhook_url: string | null;
  score_inbound_threshold: number;
  score_outbound_threshold: number;
}

export interface EnrichmentSettings {
  apollo_api_key: string | null;
  clearbit_api_key: string | null;
  proxycurl_api_key: string | null;
}

export interface ApiKeyEntry {
  key_name: string;
  is_set: boolean;
  is_active: boolean;
  last_verified_at: string | null;
}
