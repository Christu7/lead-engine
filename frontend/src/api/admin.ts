import { apiFetch } from "./client";

export interface AdminUser {
  id: number;
  email: string;
  name: string | null;
  role: string;
  is_active: boolean;
  clients: { id: number; name: string }[];
  created_at: string;
  last_login_at: string | null;
}

export interface AdminClient {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  user_count: number;
  lead_count: number;
  company_count: number;
  created_at: string;
}

export async function listAdminUsers(): Promise<AdminUser[]> {
  const res = await apiFetch("/admin/users");
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function createAdminUser(
  email: string,
  password: string,
  role: string,
  name?: string,
  clientIds?: number[],
): Promise<AdminUser> {
  const res = await apiFetch("/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      role,
      name: name || null,
      client_ids: clientIds ?? [],
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to create user");
  }
  return res.json();
}

export async function updateAdminUser(
  userId: number,
  data: { name?: string | null; role?: string; is_active?: boolean },
): Promise<AdminUser> {
  const res = await apiFetch(`/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to update user");
  }
  return res.json();
}

export async function updateUserRole(userId: number, role: string): Promise<AdminUser> {
  const res = await apiFetch(`/admin/users/${userId}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to update role");
  }
  return res.json();
}

export async function assignUserToWorkspace(userId: number, clientId: number): Promise<void> {
  const res = await apiFetch(`/admin/users/${userId}/clients`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: clientId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to assign workspace");
  }
}

export async function removeUserFromWorkspace(userId: number, clientId: number): Promise<void> {
  const res = await apiFetch(`/admin/users/${userId}/clients/${clientId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to remove from workspace");
  }
}

export async function listAdminClients(): Promise<AdminClient[]> {
  const res = await apiFetch("/admin/clients");
  if (!res.ok) throw new Error("Failed to fetch clients");
  return res.json();
}

export async function updateAdminClient(
  clientId: number,
  data: { name?: string; description?: string | null },
): Promise<AdminClient> {
  const res = await apiFetch(`/admin/clients/${clientId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to update workspace");
  }
  return res.json();
}

export async function deleteAdminClient(clientId: number): Promise<void> {
  const res = await apiFetch(`/admin/clients/${clientId}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to delete workspace");
  }
}

export interface QueueStats {
  pending: number;
  scheduled: number;
  processing: number;
  dead_letter: number;
  tasks_by_type: Record<string, number>;
  rate_limited_until: number | null;
}

export async function getQueueStats(): Promise<QueueStats> {
  const res = await apiFetch("/admin/queue-stats");
  if (!res.ok) throw new Error("Failed to fetch queue stats");
  return res.json();
}
