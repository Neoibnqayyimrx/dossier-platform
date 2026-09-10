"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ApiError, getSessionExpired, subscribeToAuthStore } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Card, ErrorNotice } from "@/components/ui";

export default function LoginPage() {
  const { status, login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // WHY useSyncExternalStore for one boolean, rather than reading
  // sessionStorage in an effect: sessionStorage IS an external store, and
  // setState inside an effect is what react-hooks/set-state-in-effect
  // (correctly) refuses. It also settles the render this page has to get
  // right -- the server has no sessionStorage, so getServerSnapshot
  // answers false there and during hydration, and React swaps in the real
  // value afterwards with no mismatch. Same pattern, same reasons, as the
  // token itself in lib/auth.tsx.
  const expired = useSyncExternalStore(
    subscribeToAuthStore,
    getSessionExpired,
    () => false,
  );

  useEffect(() => {
    if (status === "authenticated") router.replace("/projects");
  }, [status, router]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      router.replace("/projects");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not reach the server",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Sign in</h1>
      <Card>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Shown instead of the error, not alongside it: once you have
              tried to sign in, what went wrong with THAT attempt is the
              more useful thing to read. */}
          {error ? (
            <ErrorNotice message={error} />
          ) : (
            expired && (
              <div
                role="status"
                className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-200"
              >
                Your session expired, so we signed you out. Sign in again to
                pick up where you left off.
              </div>
            )
          )}

          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-1 block text-sm font-medium"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </div>

          <div className="flex items-center gap-3 pt-1">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
            <Link
              href="/register"
              className="text-sm text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
            >
              New here? Sign up
            </Link>
          </div>
        </form>
      </Card>
    </div>
  );
}
