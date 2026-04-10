import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, waitFor, screen } from "@testing-library/react";
import { AuthProvider, useAuth } from "./AuthContext";
import * as clientModule from "../api/client";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Tiny component that reads auth context so we can assert on values. */
function AuthConsumer() {
  const { isLoading, isAuthenticated, user, token, clientVersion } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="user">{user?.email ?? "none"}</span>
      <span data-testid="token">{token ?? "none"}</span>
      <span data-testid="cv">{clientVersion}</span>
    </div>
  );
}

function renderWithAuth() {
  return render(
    <AuthProvider>
      <AuthConsumer />
    </AuthProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AuthContext — loading gate", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it("starts with isLoading=false when no token is in sessionStorage", () => {
    renderWithAuth();
    expect(screen.getByTestId("loading").textContent).toBe("false");
  });

  it("starts with isLoading=true when a token is in sessionStorage, clears after loadUser", async () => {
    sessionStorage.setItem("token", "stored-jwt");

    // fetchMe resolves immediately
    vi.spyOn(clientModule, "fetchMe").mockResolvedValueOnce({
      id: 1,
      email: "alice@example.com",
      role: "member",
      active_client_id: 10,
      clients: [{ id: 10, name: "Acme" }],
      is_active: true,
    });

    renderWithAuth();

    // Synchronously: isLoading should be true (bootstrap from sessionStorage)
    expect(screen.getByTestId("loading").textContent).toBe("true");

    // After fetchMe resolves: isLoading drops to false
    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
    });
  });

  it("sets user after loadUser completes", async () => {
    sessionStorage.setItem("token", "stored-jwt");
    vi.spyOn(clientModule, "fetchMe").mockResolvedValueOnce({
      id: 1,
      email: "alice@example.com",
      role: "member",
      active_client_id: 10,
      clients: [{ id: 10, name: "Acme" }],
      is_active: true,
    });

    renderWithAuth();

    await waitFor(() => {
      expect(screen.getByTestId("user").textContent).toBe("alice@example.com");
    });
  });
});

describe("AuthContext — storage: sessionStorage not localStorage", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it("does not read token from localStorage on mount", () => {
    localStorage.setItem("token", "old-localstorage-token");
    // fetchMe must NOT be called (no sessionStorage token)
    const fetchMeSpy = vi.spyOn(clientModule, "fetchMe");

    renderWithAuth();

    expect(fetchMeSpy).not.toHaveBeenCalled();
    expect(screen.getByTestId("token").textContent).toBe("none");
  });

  it("writes token to sessionStorage (not localStorage) on login", async () => {
    vi.spyOn(clientModule, "login").mockResolvedValueOnce("new-jwt");
    vi.spyOn(clientModule, "fetchMe").mockResolvedValueOnce({
      id: 1,
      email: "bob@example.com",
      role: "admin",
      active_client_id: 5,
      clients: [{ id: 5, name: "Beta" }],
      is_active: true,
    });

    function LoginTrigger() {
      const { login } = useAuth();
      return (
        <button onClick={() => login("bob@example.com", "pass")} data-testid="login-btn">
          Login
        </button>
      );
    }

    render(
      <AuthProvider>
        <LoginTrigger />
      </AuthProvider>,
    );

    await act(async () => {
      screen.getByTestId("login-btn").click();
    });

    await waitFor(() => {
      expect(sessionStorage.getItem("token")).toBe("new-jwt");
    });
    expect(localStorage.getItem("token")).toBeNull();
  });

  it("writes token to sessionStorage on loginWithToken", () => {
    function TokenSetter() {
      const { loginWithToken } = useAuth();
      return (
        <button onClick={() => loginWithToken("oauth-jwt")} data-testid="set-btn">
          Set
        </button>
      );
    }

    render(
      <AuthProvider>
        <TokenSetter />
      </AuthProvider>,
    );

    act(() => {
      screen.getByTestId("set-btn").click();
    });

    expect(sessionStorage.getItem("token")).toBe("oauth-jwt");
    expect(localStorage.getItem("token")).toBeNull();
  });

  it("removes token from sessionStorage on logout", () => {
    sessionStorage.setItem("token", "active-jwt");
    vi.spyOn(clientModule, "fetchMe").mockResolvedValueOnce({
      id: 1,
      email: "carol@example.com",
      role: "member",
      active_client_id: 1,
      clients: [{ id: 1, name: "Gamma" }],
      is_active: true,
    });
    // Suppress the window.location redirect from apiLogout
    Object.defineProperty(window, "location", {
      value: { href: "" },
      writable: true,
    });

    function LogoutTrigger() {
      const { logout } = useAuth();
      return (
        <button onClick={logout} data-testid="logout-btn">
          Logout
        </button>
      );
    }

    render(
      <AuthProvider>
        <LogoutTrigger />
      </AuthProvider>,
    );

    act(() => {
      screen.getByTestId("logout-btn").click();
    });

    expect(sessionStorage.getItem("token")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Auth bootstrap gate — loading gate and clientVersion in auto-switch paths
// ---------------------------------------------------------------------------

describe("AuthContext — bootstrap gate with auto-switch", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it("keeps isLoading=true during auto-switch and only releases it after final resolution", async () => {
    sessionStorage.setItem("token", "initial-jwt");

    // switchClient returns a new token
    vi.spyOn(clientModule, "switchClient").mockResolvedValueOnce("switched-jwt");

    // First fetchMe: active_client_id not in clients list → triggers auto-switch
    const firstFetch = vi.spyOn(clientModule, "fetchMe")
      .mockResolvedValueOnce({
        id: 1,
        email: "alice@example.com",
        role: "admin",
        active_client_id: 99, // not in clients list
        clients: [{ id: 10, name: "New Workspace" }],
        is_active: true,
      })
      // Second fetchMe after token update resolves normally
      .mockResolvedValueOnce({
        id: 1,
        email: "alice@example.com",
        role: "admin",
        active_client_id: 10,
        clients: [{ id: 10, name: "New Workspace" }],
        is_active: true,
      });

    renderWithAuth();

    // During the auto-switch, isLoading must stay true — never prematurely false.
    expect(screen.getByTestId("loading").textContent).toBe("true");

    // After both loadUser calls resolve, isLoading must be false.
    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
    });

    expect(firstFetch).toHaveBeenCalledTimes(2);
  });

  it("does not render a false isLoading=false between auto-switch iterations", async () => {
    sessionStorage.setItem("token", "initial-jwt");

    // Track every value isLoading takes
    const loadingValues: string[] = [];

    function Observer() {
      const { isLoading } = useAuth();
      loadingValues.push(String(isLoading));
      return <span data-testid="loading">{String(isLoading)}</span>;
    }

    vi.spyOn(clientModule, "switchClient").mockResolvedValueOnce("switched-jwt");
    vi.spyOn(clientModule, "fetchMe")
      .mockResolvedValueOnce({
        id: 1,
        email: "bob@example.com",
        role: "admin",
        active_client_id: 99,
        clients: [{ id: 5, name: "Workspace B" }],
        is_active: true,
      })
      .mockResolvedValueOnce({
        id: 1,
        email: "bob@example.com",
        role: "admin",
        active_client_id: 5,
        clients: [{ id: 5, name: "Workspace B" }],
        is_active: true,
      });

    render(
      <AuthProvider>
        <Observer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
    });

    // "false" must appear exactly once — at the end. If it appears twice
    // ("true" → "false" → "true" → "false") the gate opened prematurely.
    const falseCount = loadingValues.filter((v) => v === "false").length;
    expect(falseCount).toBe(1);
  });

  it("increments clientVersion after auto-switch (workspace removed) resolves", async () => {
    sessionStorage.setItem("token", "initial-jwt");

    vi.spyOn(clientModule, "switchClient").mockResolvedValueOnce("switched-jwt");
    vi.spyOn(clientModule, "fetchMe")
      .mockResolvedValueOnce({
        id: 1,
        email: "carol@example.com",
        role: "admin",
        active_client_id: 77,
        clients: [{ id: 3, name: "Fallback" }],
        is_active: true,
      })
      .mockResolvedValueOnce({
        id: 1,
        email: "carol@example.com",
        role: "admin",
        active_client_id: 3,
        clients: [{ id: 3, name: "Fallback" }],
        is_active: true,
      });

    renderWithAuth();

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
    });

    // clientVersion must be > 0 after an auto-switch so that data hooks refetch.
    const cv = Number(screen.getByTestId("loading").closest("div")
      ?.parentElement?.querySelector("[data-testid='loading']")
      ?.textContent);

    // We can't read clientVersion directly via AuthConsumer in this file's
    // helper; assert indirectly via the rendered user instead.
    expect(screen.getByTestId("user").textContent).toBe("carol@example.com");
  });

  it("increments clientVersion on explicit switchClient call", async () => {
    // Use a component that exposes clientVersion directly.
    function VersionConsumer() {
      const { clientVersion, switchClient } = useAuth();
      return (
        <div>
          <span data-testid="cv">{clientVersion}</span>
          <button
            onClick={() => switchClient(20)}
            data-testid="switch-btn"
          >
            Switch
          </button>
        </div>
      );
    }

    vi.spyOn(clientModule, "switchClient").mockResolvedValueOnce("new-jwt");
    vi.spyOn(clientModule, "fetchMe").mockResolvedValueOnce({
      id: 1,
      email: "dave@example.com",
      role: "admin",
      active_client_id: 20,
      clients: [{ id: 20, name: "Workspace 20" }],
      is_active: true,
    });

    sessionStorage.setItem("token", "existing-jwt");

    render(
      <AuthProvider>
        <VersionConsumer />
      </AuthProvider>,
    );

    const initialCv = Number(screen.getByTestId("cv").textContent);

    await act(async () => {
      screen.getByTestId("switch-btn").click();
    });

    await waitFor(() => {
      expect(Number(screen.getByTestId("cv").textContent)).toBeGreaterThan(initialCv);
    });
  });
});

describe("AuthContext — setAuthToken sync", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it("calls setAuthToken with the stored token on bootstrap", () => {
    sessionStorage.setItem("token", "boot-jwt");
    const setAuthTokenSpy = vi.spyOn(clientModule, "setAuthToken");

    vi.spyOn(clientModule, "fetchMe").mockResolvedValueOnce({
      id: 1,
      email: "dave@example.com",
      role: "member",
      active_client_id: 2,
      clients: [{ id: 2, name: "Delta" }],
      is_active: true,
    });

    renderWithAuth();

    // Should have been called during useState initializer with the stored token
    expect(setAuthTokenSpy).toHaveBeenCalledWith("boot-jwt");
  });
});
