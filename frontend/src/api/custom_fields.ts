import { apiFetch } from "./client";
import type {
  CustomFieldDefinition,
  CustomFieldDefinitionCreate,
  CustomFieldDefinitionUpdate,
  CustomFieldValues,
} from "../types/custom_field";

export async function getCustomFieldDefinitions(
  entityType: "lead" | "company",
): Promise<CustomFieldDefinition[]> {
  const res = await apiFetch(`/custom-fields?entity_type=${entityType}`);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to fetch custom field definitions");
  }
  return res.json();
}

export async function createCustomFieldDefinition(
  data: CustomFieldDefinitionCreate,
): Promise<CustomFieldDefinition> {
  const res = await apiFetch("/custom-fields", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Failed to create custom field definition");
  }
  return res.json();
}

export async function updateCustomFieldDefinition(
  id: string,
  data: CustomFieldDefinitionUpdate,
  force = false,
): Promise<CustomFieldDefinition> {
  const res = await apiFetch(`/custom-fields/${id}?force=${force}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Failed to update custom field definition");
  }
  return res.json();
}

export async function deleteCustomFieldDefinition(id: string): Promise<void> {
  const res = await apiFetch(`/custom-fields/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Failed to delete custom field definition");
  }
}

export async function restoreCustomFieldDefinition(
  id: string,
): Promise<CustomFieldDefinition> {
  const res = await apiFetch(`/custom-fields/${id}/restore`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Failed to restore custom field definition");
  }
  return res.json();
}

export async function updateLeadCustomFields(
  leadId: number | string,
  values: CustomFieldValues,
): Promise<CustomFieldValues> {
  const res = await apiFetch(`/leads/${leadId}/custom-fields`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Failed to update lead custom fields");
  }
  return res.json();
}

export async function updateCompanyCustomFields(
  companyId: number | string,
  values: CustomFieldValues,
): Promise<CustomFieldValues> {
  const res = await apiFetch(`/companies/${companyId}/custom-fields`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Failed to update company custom fields");
  }
  return res.json();
}
