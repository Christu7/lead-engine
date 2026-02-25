export interface ScoringRule {
  id: number;
  client_id: number;
  field: string;
  operator: string;
  value: string;
  points: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ScoringRuleListResponse {
  items: ScoringRule[];
  total: number;
}

export interface ScoringTemplateRule {
  field: string;
  operator: string;
  value: string;
  points: number;
}

export interface ScoringTemplate {
  name: string;
  description: string;
  rules: ScoringTemplateRule[];
}

export const VALID_OPERATORS = [
  "equals",
  "not_equals",
  "contains",
  "not_contains",
  "greater_than",
  "less_than",
  "not_empty",
] as const;

export const OPERATOR_LABELS: Record<string, string> = {
  equals: "Equals",
  not_equals: "Not Equals",
  contains: "Contains",
  not_contains: "Not Contains",
  greater_than: "Greater Than",
  less_than: "Less Than",
  not_empty: "Not Empty",
};
