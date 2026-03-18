const API_BASE = "http://localhost:8000/api";

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem("token");
  const headers = new Headers(options.headers);

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 401) {
    localStorage.removeItem("token");
    window.location.href = "/login";
  }

  return response;
}

export async function login(email: string, password: string): Promise<void> {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!response.ok) {
    throw new Error("Invalid credentials");
  }

  const data = await response.json();
  localStorage.setItem("token", data.access_token);
}

export function logout(): void {
  localStorage.removeItem("token");
  window.location.href = "/login";
}

export function getGoogleAuthUrl(): string {
  return `${API_BASE}/auth/google`;
}

export interface AuthUser {
  id: number;
  email: string;
  role: string;
  active_client_id: number | null;
  clients: { id: number; name: string }[];
  is_active: boolean;
}

export async function fetchMe(): Promise<AuthUser> {
  const response = await apiFetch("/auth/me");
  if (!response.ok) throw new Error("Failed to fetch user");
  return response.json();
}

export async function switchClient(clientId: number): Promise<string> {
  const response = await apiFetch(`/auth/switch-client/${clientId}`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to switch client");
  const data = await response.json();
  return data.access_token;
}
