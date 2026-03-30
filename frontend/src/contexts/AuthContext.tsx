import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from "react";
import { login as apiLogin, logout as apiLogout, fetchMe, switchClient as apiSwitchClient, type AuthUser } from "../api/client";


interface AuthContextValue {
  token: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  clientVersion: number;
  login: (email: string, password: string) => Promise<void>;
  loginWithToken: (token: string) => void;
  switchClient: (clientId: number) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));
  const [user, setUser] = useState<AuthUser | null>(null);
  const [clientVersion, setClientVersion] = useState(0);

  const loadUser = useCallback(async () => {
    try {
      const me = await fetchMe();
      // If active workspace was soft-deleted, auto-switch to the first available one.
      if (
        me.active_client_id !== null &&
        me.clients.length > 0 &&
        !me.clients.some((c) => c.id === me.active_client_id)
      ) {
        const newToken = await apiSwitchClient(me.clients[0].id);
        localStorage.setItem("token", newToken);
        setToken(newToken);
        // The token useEffect will call loadUser again with the refreshed token.
        return;
      }
      // Restore last used workspace from localStorage (set on explicit switch).
      const lastIdStr = localStorage.getItem("lastWorkspaceId");
      const lastId = lastIdStr ? parseInt(lastIdStr, 10) : NaN;
      if (
        !isNaN(lastId) &&
        lastId !== me.active_client_id &&
        me.clients.some((c) => c.id === lastId)
      ) {
        const newToken = await apiSwitchClient(lastId);
        localStorage.setItem("token", newToken);
        setToken(newToken);
        return;
      }
      setUser(me);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    if (token) {
      loadUser();
    } else {
      setUser(null);
    }
  }, [token, loadUser]);

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password);
    const newToken = localStorage.getItem("token");
    setToken(newToken);
  }, []);

  const loginWithToken = useCallback((newToken: string) => {
    localStorage.setItem("token", newToken);
    setToken(newToken);
  }, []);

  const switchClient = useCallback(async (clientId: number) => {
    const newToken = await apiSwitchClient(clientId);
    localStorage.setItem("token", newToken);
    setToken(newToken);
    setClientVersion((v) => v + 1);
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, isAuthenticated: !!token, clientVersion, login, loginWithToken, switchClient, logout }}>
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
