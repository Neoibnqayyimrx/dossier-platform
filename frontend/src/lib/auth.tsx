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
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";

import { api, clearStoredToken, getStoredToken, storeToken } from "@/lib/api";
import type { User } from "@/lib/types";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  token: string | null;
  /**
   * The token's owner (email, role, ...) -- null both while signed out AND
   * for the brief window after sign-in before GET /auth/me resolves.
   * `status === "authenticated"` on its own only proves a token exists,
   * not that it's valid or who it belongs to; anything gating on role
   * (an "Admin" nav link) should check `user` too, not `status` alone.
   */
  user: User | null;
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

  const [fetchedUser, setFetchedUser] = useState<User | null>(null);

  // Layered on top of the token, not part of the sync external-store read
  // above: it's an async fetch (who does this token belong to right now),
  // not a local read, so it can't live in getSnapshot. Re-runs whenever
  // the token itself changes (sign-in, sign-out, cross-tab sign-out).
  //
  // WHY no synchronous setFetchedUser for the "not authenticated" case
  // (react-hooks/set-state-in-effect flags exactly that): `user` below
  // derives from `status` instead, so a stale fetchedUser from a previous
  // session never leaks through a logout -- nothing needs to rush in and
  // clear it before paint.
  useEffect(() => {
    if (status !== "authenticated") return;
    let cancelled = false;
    api
      .me()
      .then((current) => {
        if (!cancelled) setFetchedUser(current);
      })
      .catch(() => {
        // An expired/invalid token: leave fetchedUser as-is. AuthGuard-
        // protected pages still work off `status`; anything role-gated
        // just stays hidden via the `user` derivation below, which is the
        // safe default.
      });
    return () => {
      cancelled = true;
    };
  }, [status, token]);

  // Derived, not the raw fetch state: guarantees a signed-out (or
  // not-yet-signed-in) render can never show a previous session's user.
  const user = status === "authenticated" ? fetchedUser : null;

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password);
    // Clears out whoever the PREVIOUS token belonged to before the new one
    // takes effect -- otherwise a login-as-someone-else briefly derives
    // `user` from the prior session's fetchedUser while the fresh
    // GET /auth/me (fired by the effect above) is still in flight.
    setFetchedUser(null);
    storeToken(result.access_token);
    notify();
  }, []);

  const logout = useCallback(() => {
    clearStoredToken();
    notify();
  }, []);

  const value = useMemo(
    () => ({ status, token: token ?? null, user, login, logout }),
    [status, token, user, login, logout],
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
