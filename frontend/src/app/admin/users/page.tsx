"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { User } from "@/lib/types";
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
    <ul className="space-y-3">
      {users.map((u) => (
        <UserRow
          key={u.id}
          targetUser={u}
          isSelf={u.id === currentUser.id}
          onChange={(updated) =>
            setUsers((prev) => prev?.map((row) => (row.id === updated.id ? updated : row)) ?? null)
          }
        />
      ))}
    </ul>
  );
}

export default function AdminUsersPage() {
  return (
    <AuthGuard>
      <PageHeading
        title="Users"
        subtitle="Manage roles and account access. You can't change your own role or status here."
      />
      <UserManagement />
    </AuthGuard>
  );
}
