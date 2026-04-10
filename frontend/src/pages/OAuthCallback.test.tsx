import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import OAuthCallback from "./OAuthCallback";
import { AuthContext } from "../contexts/AuthContext";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Minimal AuthContext value — only loginWithToken matters for these tests. */
function makeAuthValue(loginWithToken = vi.fn()) {
  return {
    token: null,
    user: null,
    isAuthenticated: false,
    isLoading: false,
    clientVersion: 0,
    login: vi.fn(),
    loginWithToken,
    switchClient: vi.fn(),
    logout: vi.fn(),
  };
}

function renderCallback(hash: string, loginWithToken = vi.fn()) {
  // Set the hash before rendering
  window.location.hash = hash;

  return render(
    <AuthContext.Provider value={makeAuthValue(loginWithToken)}>
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <Routes>
          <Route path="/auth/callback" element={<OAuthCallback />} />
          <Route path="/" element={<div data-testid="home">Home</div>} />
          <Route path="/login" element={<div data-testid="login">Login</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("OAuthCallback", () => {
  beforeEach(() => {
    vi.spyOn(history, "replaceState");
    window.location.hash = "";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.location.hash = "";
  });

  it("calls loginWithToken with the token from the hash fragment", async () => {
    const loginWithToken = vi.fn();
    renderCallback("#token=my-oauth-jwt", loginWithToken);

    await waitFor(() => {
      expect(loginWithToken).toHaveBeenCalledWith("my-oauth-jwt");
    });
  });

  it("clears the hash after reading the token", async () => {
    renderCallback("#token=my-oauth-jwt");

    await waitFor(() => {
      expect(history.replaceState).toHaveBeenCalledWith(null, "", expect.not.stringContaining("#"));
    });
  });

  it("navigates to / on success", async () => {
    const { getByTestId } = renderCallback("#token=my-oauth-jwt");

    await waitFor(() => {
      expect(getByTestId("home")).toBeInTheDocument();
    });
  });

  it("navigates to /login when no token is in the hash", async () => {
    const { getByTestId } = renderCallback("#");

    await waitFor(() => {
      expect(getByTestId("login")).toBeInTheDocument();
    });
  });

  it("navigates to /login when the hash is empty", async () => {
    const { getByTestId } = renderCallback("");

    await waitFor(() => {
      expect(getByTestId("login")).toBeInTheDocument();
    });
  });

  it("does NOT call loginWithToken when there is no token", async () => {
    const loginWithToken = vi.fn();
    renderCallback("", loginWithToken);

    await waitFor(() => {
      expect(loginWithToken).not.toHaveBeenCalled();
    });
  });

  it("does not read from window.location.search for the token", async () => {
    // Simulate old query-param delivery — must NOT be accepted
    const loginWithToken = vi.fn();
    Object.defineProperty(window, "location", {
      value: { hash: "", search: "?token=from-query", pathname: "/auth/callback" },
      writable: true,
    });

    renderCallback("", loginWithToken);

    await waitFor(() => {
      expect(loginWithToken).not.toHaveBeenCalled();
    });
  });
});
