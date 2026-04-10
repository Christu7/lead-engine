// ---------------------------------------------------------------------------
// API base — read from env at call time so tests can stub it via vi.stubEnv
// ---------------------------------------------------------------------------

export function getApiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? "/api";
}

if (!import.meta.env.VITE_API_BASE_URL) {
  console.warn(
    "[leadengine] VITE_API_BASE_URL is not set — defaulting to /api. " +
      "Set this variable for production builds.",
  );
}

// ---------------------------------------------------------------------------
// In-memory token — never persisted by this module (AuthContext owns persistence)
// ---------------------------------------------------------------------------

let _token: string | null = null;

export function setAuthToken(token: string | null): void {
  _token = token;
}

// ---------------------------------------------------------------------------
// Error helper — reads backend `detail` field, falls back to a static message
// ---------------------------------------------------------------------------

/**
 * Reads the FastAPI `{ detail: "..." }` body from a non-OK response and throws
 * an Error with that message.  Falls back to `fallback` when the body is not
 * JSON or has no `detail` key.  Return type is `Promise<never>` so TypeScript
 * treats a call site as unreachable — no need for a dummy `return` after it.
 */
export async function apiError(res: Response, fallback: string): Promise<never> {
  let message = fallback;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string" && body.detail) {
      message = body.detail;
    }
  } catch {
    // response body was not JSON — keep fallback
  }
  throw new Error(message);
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  if (_token) {
    headers.set("Authorization", `Bearer ${_token}`);
  }

  const response = await fetch(`${getApiBase()}${path}`, { ...options, headers });

  if (response.status === 401) {
    setAuthToken(null);
    sessionStorage.removeItem("token");
    window.location.href = "/login";
  }

  return response;
}

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------

/** Returns the access token on success; throws with the server's error message on failure. */
export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${getApiBase()}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!response.ok) await apiError(response, "Login failed");

  const data = await response.json();
  return data.access_token as string;
}

export function logout(): void {
  setAuthToken(null);
  sessionStorage.removeItem("token");
  window.location.href = "/login";
}

export function getGoogleAuthUrl(): string {
  return `${getApiBase()}/auth/google`;
}

// ---------------------------------------------------------------------------
// User / client API
// ---------------------------------------------------------------------------

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
  if (!response.ok) await apiError(response, "Failed to fetch user");
  return response.json();
}

export async function switchClient(clientId: number): Promise<string> {
  const response = await apiFetch(`/auth/switch-client/${clientId}`, { method: "POST" });
  if (!response.ok) await apiError(response, "Failed to switch client");
  const data = await response.json();
  return data.access_token;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const response = await apiFetch("/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  if (!response.ok) await apiError(response, "Failed to change password");
}

export async function createClient(
  name: string,
  description?: string,
): Promise<{ id: number; name: string }> {
  const response = await apiFetch("/clients/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description: description || null }),
  });
  if (!response.ok) await apiError(response, "Failed to create client");
  return response.json();
}
