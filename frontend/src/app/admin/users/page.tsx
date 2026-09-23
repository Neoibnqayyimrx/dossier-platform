"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { User, UserRole } from "@/lib/types";
import { AuthGuard } from "@/components/AuthGuard";
import { Badge, Card, ErrorNotice, PageHeading } from "@/components/ui";

function UserRow({
  targetUser,
  isSelf,
  onChange,
}: {
  targetUser: User;
  isSelf: boolean;
  onChange: (updated: User) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggleRole() {
    setError(null);
    setBusy(true);
    try {
      const updated = await api.updateUser(targetUser.id, {
        role: targetUser.role === "admin" ? "user" : "admin",
      });
      onChange(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive() {
    setError(null);
    setBusy(true);
    try {
      const updated = await api.updateUser(targetUser.id, {
        is_active: !targetUser.is_active,
      });
      onChange(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-medium">
              {targetUser.email}
              {isSelf && (
                <span className="ml-2 text-sm font-normal text-slate-500 dark:text-slate-400">
                  (you)
                </span>
              )}
            </p>
            <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
              Joined {new Date(targetUser.created_at).toLocaleDateString()}
            </p>
            {error && (
              <div className="mt-2">
                <ErrorNotice message={error} />
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Badge tone={targetUser.role === "admin" ? "good" : "neutral"}>
              {targetUser.role}
            </Badge>
            <Badge tone={targetUser.is_active ? "good" : "bad"}>
              {targetUser.is_active ? "active" : "deactivated"}
            </Badge>
            {!isSelf && (
              <>
                <button
                  type="button"
                  onClick={toggleRole}
                  disabled={busy}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-slate-700"
                >
                  {targetUser.role === "admin" ? "Make user" : "Make admin"}
                </button>
                <button
                  type="button"
                  onClick={toggleActive}
                  disabled={busy}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-slate-700"
                >
                  {targetUser.is_active ? "Deactivate" : "Reactivate"}
                </button>
              </>
            )}
          </div>
        </div>
      </Card>
    </li>
  );
}

function AddMemberForm({ onAdded }: { onAdded: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("user");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setAdded(null);
    setBusy(true);
    try {
      const user = await api.addMember({ email, password, role });
      onAdded(user);
      setAdded(user.email);
      setEmail("");
      setPassword("");
      setRole("user");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h2 className="mb-1 text-base font-medium">Add a colleague</h2>
      {/* gap Phase 6a: this is the ONLY way into an existing organization --
          signing up always creates a new one. The platform sends no email,
          so the admin sets a first password and passes it on. */}
      <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">
        They join this organization and can work on the same dossiers. Give them
        the password you set here; there is no invitation email.
      </p>
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
        {error && (
          <div className="w-full">
            <ErrorNotice message={error} />
          </div>
        )}
        {added && (
          <p className="w-full text-sm text-emerald-700 dark:text-emerald-400">
            Added {added}.
          </p>
        )}
        <div className="min-w-[14rem] flex-1">
          <label htmlFor="memberEmail" className="mb-1 block text-sm font-medium">
            Email
          </label>
          <input
            id="memberEmail"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </div>
        <div className="min-w-[12rem] flex-1">
          <label htmlFor="memberPassword" className="mb-1 block text-sm font-medium">
            First password
          </label>
          {/* type="text": the admin has to read this out to the colleague, so
              masking it would only invite typos in a value they must share. */}
          <input
            id="memberPassword"
            type="text"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </div>
        <div>
          <label htmlFor="memberRole" className="mb-1 block text-sm font-medium">
            Role
          </label>
          <select
            id="memberRole"
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        </div>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
        >
          {busy ? "Adding…" : "Add member"}
        </button>
      </form>
    </Card>
  );
}


function UserManagement() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listUsers()
      .then(setUsers)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not reach the server"),
      );
  }, []);

  // Still resolving GET /auth/me -- wait rather than flash "access denied"
  // at an admin whose profile just hasn't loaded yet.
  if (currentUser === null) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }

  if (currentUser.role !== "admin") {
    return (
      <Card>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          This page is for admins only.
        </p>
      </Card>
    );
  }

  if (error) return <ErrorNotice message={error} />;
  if (users === null) return <p className="text-sm text-slate-500">Loading users…</p>;

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Accounts in <span className="font-medium">{currentUser.organization.name}</span>. Other
        organizations&apos; accounts are not listed here, and their dossiers are
        not reachable from this account.
      </p>
      <AddMemberForm onAdded={(user) => setUsers((prev) => [...(prev ?? []), user])} />
      <ul className="space-y-3">
        {users.map((u) => (
          <UserRow
            key={u.id}
            targetUser={u}
            isSelf={u.id === currentUser.id}
            onChange={(updated) =>
              setUsers(
                (prev) => prev?.map((row) => (row.id === updated.id ? updated : row)) ?? null,
              )
            }
          />
        ))}
      </ul>
    </div>
  );
}

export default function AdminUsersPage() {
  return (
    <AuthGuard>
      <PageHeading
        title="Users"
        subtitle="Manage your organization's members and their access. You can't change your own role or status here."
      />
      <UserManagement />
    </AuthGuard>
  );
}
