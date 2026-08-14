"use client";

/**
 * Auth state for the whole app: the bearer token, plus login/logout.
 *
 * WHY `useSyncExternalStore` rather than `useState` + an effect that reads
 * localStorage: localStorage IS an external store, and that is precisely
 * what this hook exists for. The obvious alternative -- setState inside a
 * mount effect -- causes a cascading re-render and is flagged by
 * react-hooks/set-state-in-effect. It also gives cross-tab logout for
 * free: the `storage` event fires in OTHER tabs, so signing out in one
 * tab signs out the rest.
 *
 * WHY the server snapshot is `undefined` while the client snapshot is
 * `string | null`: those are three genuinely different states --
 * "not read yet" (server render and the hydration pass), "signed out"
 * (null), and "signed in" (a token). Collapsing the first two into one
 * makes every guarded page flash the login screen for a frame before the
 * real token loads. React calls `getServerSnapshot` during hydration and
 * `getSnapshot` afterwards, so the transition happens on its own with no
 * effect and no extra state.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";

import { api, clearStoredToken, getStoredToken, storeToken } from "@/lib/api";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Same-tab writes must notify by hand -- the `storage` event only fires
 * in OTHER tabs, never the one that made the change. */
const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

function subscribe(onStoreChange: () => void) {
  listeners.add(onStoreChange);
  window.addEventListener("storage", onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
    window.removeEventListener("storage", onStoreChange);
  };
}

// Must return a primitive (or a cached reference): React compares
// snapshots with Object.is, so a fresh object every call would loop.
const getSnapshot = (): string | null => getStoredToken();
const getServerSnapshot = (): undefined => undefined;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const token = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );

  const status: AuthStatus =
    token === undefined ? "loading" : token ? "authenticated" : "anonymous";

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password);
    storeToken(result.access_token);
    notify();
  }, []);

  const logout = useCallback(() => {
    clearStoredToken();
    notify();
  }, []);

  const value = useMemo(
    () => ({ status, token: token ?? null, login, logout }),
    [status, token, login, logout],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used inside an <AuthProvider>");
  }
  return context;
}
