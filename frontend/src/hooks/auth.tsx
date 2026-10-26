/**
 * Sign-in state: KEEP when replacing the UI.
 *
 * <AuthProvider> asks the API who is signed in (GET /api/auth/me) and listens
 * for 401s from any call, so an expired session drops back to the login page.
 * useAuth() gives the user, their role checks and signIn / signOut.
 * Hiding a screen is only a convenience: the API enforces every role itself.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, SIGNED_OUT_EVENT } from "../api";
import type { Me, UserRole as Role } from "../api/types";

const RANK: Record<Role, number> = { viewer: 0, investigator: 1, admin: 2 };

export interface AuthState {
  /** undefined while checking; null when nobody is signed in */
  me: Me | null | undefined;
  /** set when the API could not be reached */
  error: Error | undefined;
  /** true when the signed-in user has this role or a higher one */
  can: (role: Role) => boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>();
  const [error, setError] = useState<Error>();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setError(undefined);
    api.me()
      .then(setMe)
      .catch((e: Error) => (e instanceof ApiError && e.status === 401 ? setMe(null) : setError(e)));
  }, [tick]);

  useEffect(() => {
    const onSignedOut = () => setMe(null);
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
  }, []);

  const signIn = useCallback(async (username: string, password: string) => setMe(await api.login(username, password)), []);
  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setMe(null);
    }
  }, []);
  const can = useCallback((role: Role) => !!me && RANK[me.user.role] >= RANK[role], [me]);
  const retry = useCallback(() => setTick((t) => t + 1), []);

  return <AuthContext.Provider value={{ me, error, can, signIn, signOut, retry }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
