"use client";

/**
 * Batch analysis entry (3.2.S.4.4 / 3.2.P.5.4).
 *
 * Two design commitments, both from P20's brief, and both visible in the
 * markup rather than only in the backend:
 *
 * 1. **A result cannot be recorded for a test that is not in the
 *    specification.** The result form is a list of THE SPECIFICATION'S
 *    OWN TESTS -- there is no free-text "test name" field, so there is no
 *    way to type one that does not exist. The backend refuses the same
 *    thing with a 422 (see app/api/routers/batch_results.py), which is the
 *    authority; this is what stops the filer ever reaching it.
 *
 * 2. **Out-of-specification results show at entry, not at export.** The
 *    limit is printed beside the input as it is typed, and the row is
 *    marked the moment the value breaches it. Catching a transposed digit
 *    while the certificate of analysis is still on the desk is worth far
 *    more than catching it at build time, days later.
 *
 * The check drawn here is ADVISORY and cannot gate anything -- the export
 * gate is rule R22 on the backend. See src/lib/acceptance.ts for why a
 * second copy of the comparison is tolerable and how it is pinned to the
 * original.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { evaluate } from "@/lib/acceptance";
import { ApiError, api } from "@/lib/api";
import type {
  BatchAnalysis,
  SpecificationTest,
} from "@/lib/types";

const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm " +
  "dark:border-slate-700 dark:bg-slate-900";

type BatchOwner = "drug-substance" | "drug-product";

const EMPTY_BATCH = {
  batch_number: "",
  manufacture_date: "",
  batch_size: "",
  purpose: "",
};

/** How one result reads against its limit. `null` from `evaluate` is a
 * third state, not a pass -- an unparseable pair says so rather than
 * showing a tick nobody earned. */
function verdictLabel(verdict: boolean | null) {
  if (verdict === false) {
    return {
      text: "OUT OF SPECIFICATION",
      className: "text-red-600 font-medium",
    };
  }
  if (verdict === true) {
    return { text: "Within limit", className: "text-emerald-700 dark:text-emerald-400" };
  }
  return {
    text: "Not checked automatically — read this one",
    className: "text-amber-700 dark:text-amber-400",
  };
}

export function BatchAnalysisEditor({
  owner,
  ownerId,
  ownerName,
  specification,
}: {
  owner: BatchOwner;
  ownerId: string;
  ownerName: string;
  /** The owner's own specification tests. Passed in rather than fetched
   * again so the tests offered here are provably the same rows the
   * specification editor is showing -- two fetches could disagree, and
   * "the result answers a test that is in the spec" is the invariant this
   * screen exists to hold. */
  specification: SpecificationTest[];
}) {
  const [batches, setBatches] = useState<BatchAnalysis[]>([]);
  const [draft, setDraft] = useState(EMPTY_BATCH);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const testsById = useMemo(
    () => new Map(specification.map((test) => [test.id, test])),
    [specification],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .listBatches(owner, ownerId)
      .then((loaded) => {
        if (!cancelled) setBatches(loaded);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load the batches");
      });
    return () => {
      cancelled = true;
    };
  }, [owner, ownerId]);

  const update = useCallback(
    (name: keyof typeof EMPTY_BATCH, value: string) =>
      setDraft((previous) => ({ ...previous, [name]: value })),
    [],
  );

  async function addBatch(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const saved = await api.createBatch(owner, ownerId, {
        batch_number: draft.batch_number,
        // Empty strings become null rather than being sent as "": a blank
        // date is "not recorded", and the backend's Date column would
        // reject the empty string outright.
        manufacture_date: draft.manufacture_date || null,
        batch_size: draft.batch_size || null,
        purpose: draft.purpose || null,
      });
      setBatches((previous) => [...previous, { ...saved, results: saved.results ?? [] }]);
      setDraft(EMPTY_BATCH);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the batch");
    } finally {
      setBusy(false);
    }
  }

  async function removeBatch(batchId: string) {
    try {
      await api.deleteBatch(owner, ownerId, batchId);
      setBatches((previous) => previous.filter((batch) => batch.id !== batchId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove the batch");
    }
  }

  async function recordResult(batchId: string, test: SpecificationTest, value: string) {
    if (!value.trim()) return;
    try {
      const saved = await api.createBatchResult(batchId, {
        specification_test_id: test.id,
        result: value,
        sort_order: test.sort_order,
      });
      setBatches((previous) =>
        previous.map((batch) =>
          batch.id === batchId
            ? { ...batch, results: [...batch.results, saved] }
            : batch,
        ),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the result");
    }
  }

  return (
    <div className="mt-3 rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {owner === "drug-substance" ? "3.2.S.4.4" : "3.2.P.5.4"} Batch analysis —{" "}
        {ownerName}
      </p>

      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

      {specification.length === 0 ? (
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">
          Add the specification above first. A result is an answer to a
          specification test — without the limits there is nothing for these
          numbers to be checked against.
        </p>
      ) : (
        <>
          {batches.map((batch) => (
            <BatchCard
              key={batch.id}
              batch={batch}
              specification={specification}
              testsById={testsById}
              onRecord={recordResult}
              onRemove={removeBatch}
            />
          ))}

          <form onSubmit={addBatch} className="mt-3 grid gap-2 sm:grid-cols-5">
            <input
              aria-label="Batch number"
              placeholder="EX/24/0117"
              required
              value={draft.batch_number}
              onChange={(e) => update("batch_number", e.target.value)}
              className={inputClass}
            />
            <input
              aria-label="Date of manufacture"
              type="date"
              value={draft.manufacture_date}
              onChange={(e) => update("manufacture_date", e.target.value)}
              className={inputClass}
            />
            <input
              aria-label="Batch size"
              placeholder="250,000 capsules"
              value={draft.batch_size}
              onChange={(e) => update("batch_size", e.target.value)}
              className={inputClass}
            />
            <input
              aria-label="Purpose"
              placeholder="Stability / bioequivalence"
              value={draft.purpose}
              onChange={(e) => update("purpose", e.target.value)}
              className={inputClass}
            />
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
            >
              {busy ? "Adding…" : "Add batch"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}

function BatchCard({
  batch,
  specification,
  testsById,
  onRecord,
  onRemove,
}: {
  batch: BatchAnalysis;
  specification: SpecificationTest[];
  testsById: Map<string, SpecificationTest>;
  onRecord: (batchId: string, test: SpecificationTest, value: string) => void;
  onRemove: (batchId: string) => void;
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const answered = new Set(batch.results.map((r) => r.specification_test_id));

  return (
    <div className="mb-3 rounded-md border border-slate-200 p-3 text-sm dark:border-slate-800">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium">
          {batch.batch_number}
          {batch.batch_size ? ` · ${batch.batch_size}` : ""}
          {batch.purpose ? ` · ${batch.purpose}` : ""}
        </span>
        <button
          type="button"
          onClick={() => onRemove(batch.id)}
          className="text-xs text-slate-500 hover:text-red-600"
        >
          Remove batch
        </button>
      </div>

      <table className="w-full text-left">
        <thead className="text-xs uppercase text-slate-500">
          <tr>
            <th className="py-1">Test</th>
            <th className="py-1">Acceptance criterion</th>
            <th className="py-1">Result</th>
            <th className="py-1">Against the limit</th>
          </tr>
        </thead>
        <tbody>
          {/* Driven by the SPECIFICATION, not by the results: every test
              the spec declares gets a row, so an unanswered one is visible
              as a gap rather than being absent from the screen. */}
          {specification.map((test) => {
            const recorded = batch.results.find(
              (r) => r.specification_test_id === test.id,
            );
            const value = recorded?.result ?? drafts[test.id] ?? "";
            const limit = testsById.get(test.id)?.acceptance_criterion ?? "";
            const verdict = value.trim() ? evaluate(limit, value) : null;
            const label = verdictLabel(verdict);
            return (
              <tr key={test.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1 pr-2">{test.test_name}</td>
                {/* The limit is printed next to the input, not on another
                    screen: a limit and the number judged against it belong
                    a centimetre apart. */}
                <td className="py-1 pr-2 text-slate-600 dark:text-slate-400">{limit}</td>
                <td className="py-1 pr-2">
                  {recorded ? (
                    value
                  ) : (
                    <input
                      aria-label={`Result for ${test.test_name}`}
                      value={drafts[test.id] ?? ""}
                      onChange={(e) =>
                        setDrafts((previous) => ({
                          ...previous,
                          [test.id]: e.target.value,
                        }))
                      }
                      onBlur={(e) => onRecord(batch.id, test, e.target.value)}
                      className={inputClass}
                    />
                  )}
                </td>
                <td className="py-1">
                  {value.trim() ? (
                    <span className={label.className}>{label.text}</span>
                  ) : (
                    <span className="text-slate-400">Not tested</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {answered.size < specification.length && (
        <p className="mt-2 text-xs text-slate-500">
          {specification.length - answered.size} test(s) not yet answered for
          this batch. They will render as “Not tested”, which is a declared
          position — not a blank.
        </p>
      )}
    </div>
  );
}
