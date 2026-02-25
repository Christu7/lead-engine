import { apiFetch } from "./client";
import type { DashboardStats } from "../types/dashboard";

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const res = await apiFetch("/dashboard/stats");
  if (!res.ok) throw new Error("Failed to fetch dashboard stats");
  return res.json();
}
