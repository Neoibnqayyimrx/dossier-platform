"use client";

/**
 * The 3.2.S.4.1 specification table for ONE active ingredient.
 *
 * WHY this is nested inside the active-ingredient step rather than being a
 * step of its own: 3.2.S is repeated per drug substance, so a combination
 * product has one complete specification per active. A flat "Specifications"
 * step would have to ask "which substance?" on every row, which is exactly
 * the ambiguity the nesting removes.
 *
 * The previous version of this data was a single free-text box. It read
 * fine and could not be used: nothing could render it as the table
 * 3.2.S.4.1 is required to contain, cite a method against it, or check it.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { SpecificationTest } from "@/lib/types";

const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm " +
  "dark:border-slate-700 dark:bg-slate-900";

const EMPTY = { test_name: "", method: "", acceptance_criterion: "" };

export function SpecificationEditor({
  apiId,
  substanceName,
}: {
  apiId: string;
  substanceName: string;
}) {
  const [rows, setRows] = useState<SpecificationTest[]>([]);
  const [draft, setDraft] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .listSpecificationTests(apiId)
      .then((loaded) => {
        if (!cancelled) setRows(loaded);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load the specification");
      });
    return () => {
      cancelled = true;
    };
  }, [apiId]);

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
      const saved = await api.createSpecificationTest(apiId, {
        ...draft,
        // Rows keep the order they were entered in: specification tables
        // are conventionally ordered (description, identification, assay,
        // impurities) and an assessor reads release against stability data
        // side by side, so the order is content, not presentation.
        sort_order: rows.length,
      });
      setRows((previous) => [...previous, saved]);
      setDraft(EMPTY);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the test");
    } finally {
      setBusy(false);
    }
  }

  async function remove(rowId: string) {
    try {
      await api.deleteSpecificationTest(apiId, rowId);
      setRows((previous) => previous.filter((row) => row.id !== rowId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove the test");
    }
  }

  return (
    <div className="mt-3 rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        3.2.S.4.1 Specification — {substanceName}
      </p>

      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

      {rows.length === 0 ? (
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">
          No tests yet. Every active ingredient needs a specification before
          the dossier can be exported (rule R07).
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
