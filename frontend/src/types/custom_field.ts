export interface CustomFieldDefinition {
  id: string
  client_id: number
  entity_type: "lead" | "company"
  field_key: string
  field_label: string
  field_type: "text" | "number" | "date" | "boolean" | "select"
  options: string[] | null
  is_required: boolean
  show_in_table: boolean
  sort_order: number
  enrichment_source: string | null
  enrichment_mapping: string | null
  created_at: string
  updated_at: string
}

export type CustomFieldValues = Record<string, string | number | boolean | null>

export interface CustomFieldDefinitionCreate {
  entity_type: "lead" | "company"
  field_key: string
  field_label: string
  field_type: "text" | "number" | "date" | "boolean" | "select"
  options?: string[] | null
  is_required?: boolean
  show_in_table?: boolean
  sort_order?: number
  enrichment_source?: string | null
  enrichment_mapping?: string | null
}

export interface CustomFieldDefinitionUpdate {
  field_label?: string
  field_type?: "text" | "number" | "date" | "boolean" | "select"
  options?: string[] | null
  is_required?: boolean
  show_in_table?: boolean
  sort_order?: number
  enrichment_source?: string | null
  enrichment_mapping?: string | null
}
