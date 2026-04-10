import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import {
  login as apiLogin,
  logout as apiLogout,
  fetchMe,
  setAuthToken,
  switchClient as apiSwitchClient,
  type AuthUser,
} from "../api/client";

interface AuthContextValue {
  token: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  clientVersion: number;
  login: (email: string, password: string) => Promise<void>;
  loginWithToken: (token: string) => void;
  switchClient: (clientId: number) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function storeToken(token: string): void {
  setAuthToken(token);
  sessionStorage.setItem("token", token);
}

function clearToken(): void {
  setAuthToken(null);
  sessionStorage.removeItem("token");
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  // Bootstrap from sessionStorage so a page refresh restores the session.
  const [token, setToken] = useState<string | null>(() => {
    const stored = sessionStorage.getItem("token");
    if (stored) {
      // Sync the module-level token immediately so the first apiFetch is authenticated.
      setAuthToken(stored);
    }
    return stored;
  });

  const [user, setUser] = useState<AuthUser | null>(null);
  const [clientVersion, setClientVersion] = useState(0);

  // isLoading is true until the first loadUser() resolves to a known user (or failure).
  // Initialise to true only when we have a stored token to verify.
  const [isLoading, setIsLoading] = useState<boolean>(
    () => !!sessionStorage.getItem("token"),
  );

  const loadUser = useCallback(async () => {
    setIsLoading(true);

    // When loadUser short-circuits to switch workspaces, it calls setToken() which
    // re-triggers this effect.  We must NOT clear isLoading until the final
    // resolution so the loading gate never opens prematurely.
    let redirecting = false;

    try {
      const me = await fetchMe();

      // Active workspace was removed — auto-switch to the first available one.
      if (
        me.active_client_id !== null &&
        me.clients.length > 0 &&
        !me.clients.some((c) => c.id === me.active_client_id)
      ) {
        const newToken = await apiSwitchClient(me.clients[0].id);
        storeToken(newToken);
        setToken(newToken);
        // Bump so data hooks know the workspace changed once this resolves.
        setClientVersion((v) => v + 1);
        redirecting = true;
        return;
      }

      // Restore last used workspace from localStorage (convenience, not security).
      const lastIdStr = localStorage.getItem("lastWorkspaceId");
      const lastId = lastIdStr ? parseInt(lastIdStr, 10) : NaN;
      if (
        !isNaN(lastId) &&
        lastId !== me.active_client_id &&
        me.clients.some((c) => c.id === lastId)
      ) {
        const newToken = await apiSwitchClient(lastId);
        storeToken(newToken);
        setToken(newToken);
        setClientVersion((v) => v + 1);
        redirecting = true;
        return;
      }

      setUser(me);
    } catch {
      setUser(null);
    } finally {
      // Only release the loading gate when we're done — not when we're about
      // to fire another loadUser call via a token change.
      if (!redirecting) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (token) {
      loadUser();
    } else {
      setUser(null);
      setIsLoading(false);
    }
  }, [token, loadUser]);

  const login = useCallback(async (email: string, password: string) => {
    const newToken = await apiLogin(email, password);
    storeToken(newToken);
    setToken(newToken);
  }, []);

  const loginWithToken = useCallback((newToken: string) => {
    storeToken(newToken);
    setToken(newToken);
  }, []);

  const switchClient = useCallback(async (clientId: number) => {
    const newToken = await apiSwitchClient(clientId);
    storeToken(newToken);
    setToken(newToken);
    setClientVersion((v) => v + 1);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setToken(null);
    setUser(null);
    apiLogout();
  }, []);

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        isAuthenticated: !!token,
        isLoading,
        clientVersion,
        login,
        loginWithToken,
        switchClient,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
