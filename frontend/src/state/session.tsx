import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, setUnauthorizedHandler, tokenStore } from "../api/client";
import type { Session, User } from "../api/types";

interface SessionValue {
  user: User | null;
  ready: boolean;
  signIn: (identifier: string, password: string) => Promise<void>;
  signOut: () => void;
  isStaff: boolean;
  isAdmin: boolean;
}

const Ctx = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const signOut = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  const signIn = useCallback(async (identifier: string, password: string) => {
    const session = (await api.login(identifier, password)) as Session & User;
    tokenStore.set(session.access_token, session.refresh_token);
    const { access_token: _a, refresh_token: _r, expires_in: _e, ...profile } = session;
    setUser(profile as User);
  }, []);

  useEffect(() => {
    // A stale token should silently log out, not throw on every render.
    setUnauthorizedHandler(() => setUser(null));
    if (!tokenStore.get()) {
      setReady(true);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setReady(true));
  }, []);

  const value = useMemo<SessionValue>(
    () => ({
      user,
      ready,
      signIn,
      signOut,
      isStaff: !!user && user.role !== "citizen",
      isAdmin: !!user && (user.role === "district_admin" || user.role === "system_admin"),
    }),
    [user, ready, signIn, signOut],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}
