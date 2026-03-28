import { apiFetch } from "./client";

export interface AdminUser {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface AdminClient {
  id: number;
  name: string;
  user_count: number;
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
): Promise<AdminUser> {
  const res = await apiFetch("/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, role }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to create user");
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

export async function listAdminClients(): Promise<AdminClient[]> {
  const res = await apiFetch("/admin/clients");
  if (!res.ok) throw new Error("Failed to fetch clients");
  return res.json();
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
