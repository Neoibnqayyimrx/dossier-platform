"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Card, ErrorNotice } from "@/components/ui";

export default function RegisterPage() {
  const { status, login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "authenticated") router.replace("/projects");
  }, [status, router]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    // Checked client-side only -- confirmPassword never travels to the
    // backend, /auth/register only ever sees one password field.
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    setBusy(true);
    try {
      await api.register(
        email,
        password,
        organizationName.trim() || undefined,
      );
      // Register-then-login rather than sending the user to /login: the
      // backend has no email verification step, so there's no reason to
      // make someone type their password twice in a row.
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
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Sign up</h1>
      <Card>
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && <ErrorNotice message={error} />}

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
              htmlFor="organizationName"
              className="mb-1 block text-sm font-medium"
            >
              Organization{" "}
              <span className="font-normal text-slate-500 dark:text-slate-400">
                (optional)
              </span>
            </label>
            <input
              id="organizationName"
              type="text"
              maxLength={200}
              value={organizationName}
              onChange={(e) => setOrganizationName(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            {/* gap Phase 6a: signing up creates a NEW organization and makes
                you its admin. Joining one that already exists is that
                organization admin's decision, on the Users page -- which is
                why this field never offers a list to pick from. */}
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Your company. You&apos;ll be its first admin and can add
              colleagues afterwards. To join an organization that already uses
              the platform, ask its admin to add you.
            </p>
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
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </div>

          <div>
            <label
              htmlFor="confirmPassword"
              className="mb-1 block text-sm font-medium"
            >
              Confirm password
            </label>
            <input
              id="confirmPassword"
              type="password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </div>

          <div className="flex items-center gap-3 pt-1">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
            >
              {busy ? "Signing up…" : "Sign up"}
            </button>
            <Link
              href="/login"
              className="text-sm text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
            >
              Already have an account? Sign in
            </Link>
          </div>
        </form>
      </Card>
    </div>
  );
}
