"use client";

/**
 * Recording and retracting validation overrides.
 *
 * WHY this is open to any project owner rather than gated behind the
 * admin role: `UserRole.ADMIN` means "may manage accounts", and reusing
 * it here would quietly make one bit mean two unrelated jobs — identity
 * administration and regulatory sign-off. The principle behind "who may
 * approve" is segregation of duties (the author of the data should not be
 * the sole approver of bypassing a check on it), and that needs a
 * project-scoped role, not the account-admin bit. With one user per
 * dossier, an admin gate would only mean the same person promotes
 * themselves — theatre, which is worse than an honest open control
 * because it looks like a safeguard.
 *
 * The control here is the audit trail and visibility: who, why, when,
 * reviewable afterwards, and named on every build that relied on it.
 */

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Finding, ValidationOverride } from "@/lib/types";
import { Badge, Card, ErrorNotice } from "@/components/ui";

/** Mirrors ValidationOverrideCreate.reason's min_length on the backend --
 * the server is still the one that enforces it; this only spares someone
 * a round-trip to be told. */
const MIN_REASON = 20;

function WaiveForm({
  projectId,
  ruleId,
  onDone,
}: {
  projectId: string;
  ruleId: string;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.createOverride(projectId, ruleId, reason);
      setReason("");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-2 space-y-2">
      {error && <ErrorNotice message={error} />}
      <label htmlFor={`reason-${ruleId}`} className="block text-xs font-medium">
        Why is this acceptable for this filing?
      </label>
      <textarea
        id={`reason-${ruleId}`}
        rows={2}
        required
        minLength={MIN_REASON}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Reviewed with QA: the certificate is in hand and will be attached before submission."
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
      />
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Recorded against your account and named on every package built
        while it stands.
      </p>
      <button
        type="submit"
        disabled={busy || reason.trim().length < MIN_REASON}
        className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
      >
        {busy ? "Recording…" : "Record override"}
      </button>
    </form>
  );
}

export function OverridePanel({
  projectId,
  findings,
  overrides,
  onChanged,
}: {
  projectId: string;
  findings: Finding[];
  overrides: ValidationOverride[];
  onChanged: () => void;
}) {
  const [waiving, setWaiving] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const standing = overrides.filter((o) => o.withdrawn_at === null);
  const withdrawn = overrides.filter((o) => o.withdrawn_at !== null);
  const standingRuleIds = new Set(standing.map((o) => o.rule_id));

  // One entry per blocking rule, not per finding: an override excuses the
  // RULE for this project, so offering the same waiver twice because a
  // rule fired on two values would be misleading.
  const blocking = [
    ...new Set(
      findings.filter((f) => f.severity === "ERROR").map((f) => f.rule_id),
    ),
  ].filter((ruleId) => !standingRuleIds.has(ruleId));

  async function withdraw(overrideId: string) {
    setError(null);
    setBusy(overrideId);
    try {
      await api.withdrawOverride(projectId, overrideId);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Overrides
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          An override lets a package be exported despite a deterministic
          error. It does not fix the data or hide the finding — it records
          that a human decided this one is acceptable, and why.
        </p>
      </div>

      {error && <ErrorNotice message={error} />}

      {blocking.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
            Blocking export
          </h3>
          <ul className="space-y-2">
            {blocking.map((ruleId) => (
              <li
                key={ruleId}
                className="rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-sm">{ruleId}</span>
                  <button
                    type="button"
                    onClick={() => setWaiving(waiving === ruleId ? null : ruleId)}
                    className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium dark:border-slate-700"
                  >
                    {waiving === ruleId ? "Cancel" : "Override…"}
                  </button>
                </div>
                {waiving === ruleId && (
                  <WaiveForm
                    projectId={projectId}
                    ruleId={ruleId}
                    onDone={() => {
                      setWaiving(null);
                      onChanged();
                    }}
                  />
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {standing.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
            Standing
          </h3>
          <ul className="space-y-2">
            {standing.map((override) => (
              <li
                key={override.id}
                className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900 dark:bg-amber-950/40"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="text-sm">
                    <span className="font-mono">{override.rule_id}</span>
                    <p className="mt-0.5 text-slate-700 dark:text-slate-300">
                      {override.reason}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                      Recorded {new Date(override.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={busy === override.id}
                    onClick={() => withdraw(override.id)}
                    className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-slate-700"
                  >
                    Withdraw
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {withdrawn.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
            Withdrawn
          </h3>
          {/* Kept visible on purpose: a package built while one of these
              stood is only explicable if the record survives it. */}
          <ul className="space-y-1 text-xs text-slate-500 dark:text-slate-400">
            {withdrawn.map((override) => (
              <li key={override.id}>
                <span className="font-mono">{override.rule_id}</span> — {override.reason}{" "}
                <Badge>withdrawn</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}

      {blocking.length === 0 && standing.length === 0 && (
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Nothing is being waived, and nothing is blocking export. This is
          the state a filing should reach on its data alone.
        </p>
      )}
    </Card>
  );
}
