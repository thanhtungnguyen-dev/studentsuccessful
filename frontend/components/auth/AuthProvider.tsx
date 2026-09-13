"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { apiClient, authErrorMessage, type CurrentUser } from "../../lib/api/client";

type AuthContextValue = {
  user: CurrentUser | null | undefined;
  error: string;
  refresh: () => Promise<CurrentUser | null>;
};
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>();
  const [error, setError] = useState("");
  const requestNumber = useRef(0);
  const refresh = useCallback(async () => {
    const request = ++requestNumber.current;
    try {
      const current = await apiClient.getCurrentUser();
      if (request === requestNumber.current) { setUser(current); setError(""); }
      return current;
    } catch (error) {
      if (request === requestNumber.current) { setUser(undefined); setError(authErrorMessage(error)); }
      throw error;
    }
  }, []);

  useEffect(() => {
    const check = () => { void refresh().catch(() => {}); };
    check();
    // Shared cookies may change in another tab; recheck with the server on return.
    window.addEventListener("focus", check);
    window.addEventListener("pageshow", check);
    return () => {
      ++requestNumber.current;
      window.removeEventListener("focus", check);
      window.removeEventListener("pageshow", check);
    };
  }, [refresh]);
  return <AuthContext.Provider value={{ user, error, refresh }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("AuthProvider is required");
  return context;
}
