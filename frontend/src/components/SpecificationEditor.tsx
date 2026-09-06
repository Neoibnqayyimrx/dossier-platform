"use client";

/**
 * The specification table for ONE owner -- a drug substance (3.2.S.4.1),
 * an excipient (3.2.P.4.1) or the finished product (3.2.P.5.1).
 *
 * P20 generalised this from the drug-substance-only editor P13 wrote. The
 * reasoning is the backend's, one layer up (see app/models/spec_owner.py):
 * a specification is ONE artifact the CTD asks for of three different
 * things, and three editors that drift is the failure mode. One editor
 * means one place where the "cite the method, never paste the monograph"
 * warning lives, one place row order is decided, one place a validation
 * message is worded.
 *
 * WHY the drug-substance and excipient editors stay NESTED inside their
 * owner's row rather than becoming a step of their own: 3.2.S.4.1 and
 * 3.2.P.4.1 repeat per subject, so a flat "Specifications" step would have
 * to ask "which substance?" on every row -- exactly the ambiguity the
 * nesting removes. The drug PRODUCT's specification does not repeat, so it
 * is the one that can sensibly stand alone.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import {
  SPECIFICATION_SECTION,
  type SpecificationOwnerKind,
  type SpecificationTest,
} from "@/lib/types";

const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm " +
  "dark:border-slate-700 dark:bg-slate-900";

const EMPTY = { test_name: "", method: "", acceptance_criterion: "" };

/** What an empty specification means, per owner. Only the drug substance's
 * is a blocking rule today (R07), so the other two say what is missing
 * without claiming an error the backend would not raise. */
const EMPTY_HINT: Record<SpecificationOwnerKind, string> = {
  "drug-substance":
    "No tests yet. Every active ingredient needs a specification before the dossier can be exported (rule R07).",
  "drug-product":
    "No tests yet. Without them 3.2.P.5.1 cannot be rendered, and batch results have no limits to be checked against.",
  excipient:
    "No tests yet. Each excipient owes its own 3.2.P.4.1 -- usually its monograph plus whatever this formulation depends on.",
};

export function SpecificationEditor({
  owner,
  ownerId,
  ownerName,
  onRowsChange,
}: {
  owner: SpecificationOwnerKind;
  ownerId: string;
  ownerName: string;
  /** Lets a parent (the batch screen) see the tests a result may answer,
   * without fetching them a second time and risking a different answer. */
  onRowsChange?: (rows: SpecificationTest[]) => void;
}) {
  const [rows, setRows] = useState<SpecificationTest[]>([]);
  const [draft, setDraft] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const publish = useCallback(
    (next: SpecificationTest[]) => {
      setRows(next);
      onRowsChange?.(next);
    },
    [onRowsChange],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .listSpecificationTests(owner, ownerId)
      .then((loaded) => {
        if (!cancelled) publish(loaded);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load the specification");
      });
    return () => {
      cancelled = true;
    };
  }, [owner, ownerId, publish]);

  const update = useCallback(
    (name: keyof typeof EMPTY, value: string) =>
      setDraft((previous) => ({ ...previous, [name]: value })),
    [],
  );

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const saved = await api.createSpecificationTest(owner, ownerId, {
        ...draft,
        // Rows keep the order they were entered in: specification tables
        // are conventionally ordered (description, identification, assay,
        // impurities) and an assessor reads release against stability data
        // side by side, so the order is content, not presentation.
        sort_order: rows.length,
      });
      publish([...rows, saved]);
      setDraft(EMPTY);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the test");
    } finally {
      setBusy(false);
    }
  }

  async function remove(rowId: string) {
    try {
      await api.deleteSpecificationTest(owner, ownerId, rowId);
      publish(rows.filter((row) => row.id !== rowId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove the test");
    }
  }

  return (
    <div className="mt-3 rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {SPECIFICATION_SECTION[owner]} Specification — {ownerName}
      </p>

      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

      {rows.length === 0 ? (
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">
          {EMPTY_HINT[owner]}
        </p>
      ) : (
        <table className="mb-3 w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              <th className="py-1">Test</th>
              <th className="py-1">Method</th>
              <th className="py-1">Acceptance criterion</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1 pr-2">{row.test_name}</td>
                <td className="py-1 pr-2">{row.method}</td>
                <td className="py-1 pr-2">{row.acceptance_criterion}</td>
                <td className="py-1 text-right">
                  <button
                    type="button"
                    onClick={() => remove(row.id)}
                    className="text-xs text-slate-500 hover:text-red-600"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <form onSubmit={add} className="grid gap-2 sm:grid-cols-4">
        <input
          aria-label="Test"
          placeholder="Assay"
          required
          value={draft.test_name}
          onChange={(e) => update("test_name", e.target.value)}
          className={inputClass}
        />
        <input
          aria-label="Method"
          placeholder="HPLC, BP monograph"
          required
          value={draft.method}
          onChange={(e) => update("method", e.target.value)}
          className={inputClass}
        />
        <input
          aria-label="Acceptance criterion"
          placeholder="98.0 - 102.0 % w/w"
          required
          value={draft.acceptance_criterion}
          onChange={(e) => update("acceptance_criterion", e.target.value)}
          className={inputClass}
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
        >
          {busy ? "Adding…" : "Add test"}
        </button>
      </form>

      <p className="mt-2 text-xs text-slate-500">
        Cite the method — never paste monograph text. Pharmacopoeias are
        copyrighted.
      </p>
    </div>
  );
}
