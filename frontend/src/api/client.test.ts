import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { getApiBase, setAuthToken, apiFetch, login } from "./client";

// ---------------------------------------------------------------------------
// getApiBase
// ---------------------------------------------------------------------------

describe("getApiBase", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns /api when VITE_API_BASE_URL is not set", () => {
    vi.stubEnv("VITE_API_BASE_URL", undefined as unknown as string);
    expect(getApiBase()).toBe("/api");
  });

  it("returns the env var value when VITE_API_BASE_URL is set", () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.com");
    expect(getApiBase()).toBe("https://api.example.com");
  });
});

// ---------------------------------------------------------------------------
// apiFetch — uses module token, not localStorage
// ---------------------------------------------------------------------------

describe("apiFetch", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    // Clear any token left from a previous test
    setAuthToken(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("sends Authorization header when token is set", async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

    setAuthToken("test-jwt");
    await apiFetch("/some/path");

    const [, init] = mockFetch.mock.calls[0];
    const headers = new Headers((init as RequestInit).headers);
    expect(headers.get("Authorization")).toBe("Bearer test-jwt");
  });

  it("does NOT send Authorization header when no token is set", async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

    setAuthToken(null);
    await apiFetch("/some/path");

    const [, init] = mockFetch.mock.calls[0];
    const headers = new Headers((init as RequestInit).headers);
    expect(headers.has("Authorization")).toBe(false);
  });

  it("does not read from localStorage for the token", async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

    // Put something in localStorage — apiFetch must NOT use it
    localStorage.setItem("token", "from-localstorage");
    setAuthToken(null);
    await apiFetch("/some/path");
    localStorage.removeItem("token");

    const [, init] = mockFetch.mock.calls[0];
    const headers = new Headers((init as RequestInit).headers);
    expect(headers.has("Authorization")).toBe(false);
  });

  it("builds the URL from getApiBase()", async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

    vi.stubEnv("VITE_API_BASE_URL", "https://backend.internal");
    await apiFetch("/leads");

    const [url] = mockFetch.mock.calls[0];
    expect(url).toBe("https://backend.internal/leads");
  });

  it("clears token and sessionStorage on 401", async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValueOnce(new Response("{}", { status: 401 }));

    // Suppress window.location redirect in jsdom
    Object.defineProperty(window, "location", {
      value: { href: "" },
      writable: true,
    });

    sessionStorage.setItem("token", "stale-token");
    setAuthToken("stale-token");
    await apiFetch("/protected");

    expect(sessionStorage.getItem("token")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// login — returns token, does not touch localStorage
// ---------------------------------------------------------------------------

describe("login", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("returns the access token on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: "jwt-abc" }), { status: 200 }),
      ),
    );

    const token = await login("user@example.com", "pass");
    expect(token).toBe("jwt-abc");
  });

  it("does not write to localStorage", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: "jwt-abc" }), { status: 200 }),
      ),
    );

    await login("user@example.com", "pass");
    expect(localStorage.getItem("token")).toBeNull();
  });

  it("throws on non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(new Response("{}", { status: 401 })),
    );

    await expect(login("bad@example.com", "wrong")).rejects.toThrow("Login failed");
  });
});
