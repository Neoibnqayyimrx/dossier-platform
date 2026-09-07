"use client";

/**
 * Stability data entry (3.2.S.7.3 / 3.2.P.8.3).
 *
 * ## Why this is a grid and not a wizard step
 *
 * Every other collection in this wizard is a list of rows entered through
 * one generic form driven by `wizard-steps.ts`'s field specs. That shape
 * is deliberate and it has paid off five times over -- adding a field is a
 * one-line edit, and six collections share one component.
 *
 * Stability is where it stops working, and the reason is arithmetic. A
 * real study is five timepoints across eight tests: forty values. Through
 * the generic pattern that is forty trips round an "add row" form, each
 * asking again which test and which timepoint this value is for -- and the
 * two questions the form would have to ask are exactly the two the grid
 * answers by POSITION. A filer looking at a cell in row "Dissolution",
 * column "12 months" cannot enter it against the wrong test.
 *
 * ## What the deviation costs
 *
 * Real things, and they should be recorded rather than waved past:
 *
 *   1. **A second entry idiom to learn.** Everything else in the wizard
 *      is add-a-row; this is fill-a-table. Someone who has used the
 *      first five steps does not already know how to use this one.
 *   2. **Field specs no longer describe the whole wizard.** Before this,
 *      `wizard-steps.ts` was a complete answer to "what does the wizard
 *      ask for". Now it is an answer with a footnote, and the next person
 *      adding a field has to know the footnote exists. `CHILD_STEPS`'
 *      stability entry says so where they will actually look.
 *   3. **It is a second place validation is drawn.** Mitigated the same
 *      way the batch screen's is: the check here is `src/lib/acceptance`,
 *      the same module, and it is advisory -- rule R23 on the backend is
 *      the export gate.
 *
 * The trade is worth making exactly once, here, because the shape of the
 * DATA is a table. It is not a licence to hand-write the next screen.
 *
 * ## The paste
 *
 * Every stability dataset in existence starts life in a spreadsheet. The
 * grid accepts a paste of one -- timepoints across the top, test names
 * down the side, which is the layout on screen and the layout ICH Q1A(R2)'s
 * own example tables use. Anything it cannot match is REPORTED, never
 * guessed at: guessing which test a value answers is guessing which limit
 * it will be judged against. See `src/lib/paste-table.ts`.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { evaluate } from "@/lib/acceptance";
import { ApiError, api } from "@/lib/api";
import { mapPastedTable, parsePastedTable } from "@/lib/paste-table";
import {
  STABILITY_SECTION,
  type BatchAnalysis,
  type SpecificationTest,
  type StabilityOwnerKind,
  type StabilityStudy,
} from "@/lib/types";

const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm " +
  "dark:border-slate-700 dark:bg-slate-900";

/** ICH Q1A(R2)'s own testing frequency, offered as the default columns:
 * every three months in the first year, every six in the second, annually
 * after. A filer with a different protocol edits the list. */
const DEFAULT_TIMEPOINTS = [0, 3, 6, 9, 12, 18, 24];

const EMPTY_STUDY = {
  study_type: "long-term",
  condition: "30C/65%RH",
  duration_months: "24",
  batch_analysis_id: "",
};

/** How one cell reads against its limit. `null` from `evaluate` is a third
 * state, not a pass -- an unparseable pair says so rather than showing a
 * tick nobody earned. */
function cellClass(verdict: boolean | null, empty: boolean): string {
  if (empty) return "";
  if (verdict === false) return "border-red-500 bg-red-50 dark:bg-red-950";
  if (verdict === true) return "border-emerald-400";
  return "border-amber-400";
}

type Draft = Record<string, string>;

/** A cell's key. Test and timepoint together ARE the cell's identity --
 * the same pair the database makes unique. */
const cellKey = (testId: string, months: number) => `${testId}@${months}`;

export function StabilityGrid({
  owner,
  ownerId,
  ownerName,
  specification,
  batches,
}: {
  owner: StabilityOwnerKind;
  ownerId: string;
  ownerName: string;
  /** The owner's own specification tests -- the ROWS of the grid, and the
   * only tests a result may answer. Passed in rather than fetched again so
   * they are provably the same rows the specification editor is showing. */
  specification: SpecificationTest[];
  /** The owner's batches. A study is run ON one of them, and the select
   * offers only these, so a study cannot name a batch the dossier does not
   * file in 3.2.S.4.4 / 3.2.P.5.4. */
  batches: BatchAnalysis[];
}) {
  const [studies, setStudies] = useState<StabilityStudy[]>([]);
  const [draft, setDraft] = useState<Draft>(EMPTY_STUDY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .listStabilityStudies(owner, ownerId)
      .then((loaded) => {
        if (!cancelled) setStudies(loaded);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load the stability studies");
      });
    return () => {
      cancelled = true;
    };
  }, [owner, ownerId]);

  const update = useCallback(
    (name: string, value: string) =>
      setDraft((previous) => ({ ...previous, [name]: value })),
    [],
  );

  async function addStudy(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const saved = await api.createStabilityStudy(owner, ownerId, {
        study_type: draft.study_type,
        condition: draft.condition,
        duration_months: Number.parseInt(draft.duration_months, 10) || 0,
        // Empty string becomes null: a study whose batch has not been
        // entered yet is a legitimate half-finished state, and "" is not
        // a uuid.
        batch_analysis_id: draft.batch_analysis_id || null,
      });
      setStudies((previous) => [...previous, { ...saved, results: saved.results ?? [] }]);
      setDraft(EMPTY_STUDY);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the study");
    } finally {
      setBusy(false);
    }
  }

  async function removeStudy(studyId: string) {
    try {
      await api.deleteStabilityStudy(owner, ownerId, studyId);
      setStudies((previous) => previous.filter((study) => study.id !== studyId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove the study");
    }
  }

  function replaceStudy(saved: StabilityStudy) {
    setStudies((previous) =>
      previous.map((study) => (study.id === saved.id ? saved : study)),
    );
  }

  return (
    <div className="mt-3 rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {STABILITY_SECTION[owner]} Stability data — {ownerName}
      </p>

      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

      {specification.length === 0 ? (
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">
          Add the specification above first. A stability result is an answer
          to a specification test — without the limits there is nothing for
          these numbers to be checked against, and nothing to justify a{" "}
          {owner === "drug-product" ? "shelf life" : "retest period"} with.
        </p>
      ) : (
        <>
          {studies.map((study) => (
            <StudyGrid
              key={study.id}
              study={study}
              specification={specification}
              onSaved={replaceStudy}
              onRemove={removeStudy}
            />
          ))}

          <form onSubmit={addStudy} className="mt-3 grid gap-2 sm:grid-cols-5">
            <select
              aria-label="Study type"
              value={draft.study_type}
              onChange={(e) => update("study_type", e.target.value)}
              className={inputClass}
            >
              <option value="long-term">long-term</option>
              <option value="accelerated">accelerated</option>
              <option value="intermediate">intermediate</option>
            </select>
            <input
              aria-label="Storage condition"
              placeholder="30C/65%RH"
              required
              value={draft.condition}
              onChange={(e) => update("condition", e.target.value)}
              className={inputClass}
            />
            <input
              aria-label="Duration (months)"
              type="number"
              placeholder="24"
              required
              value={draft.duration_months}
              onChange={(e) => update("duration_months", e.target.value)}
              className={inputClass}
            />
            {/* Only this owner's own batches. A study naming a batch the
                dossier does not file would put a stability table in front
                of an assessor that 3.2.P.5.4 cannot corroborate. */}
            <select
              aria-label="Batch"
              value={draft.batch_analysis_id}
              onChange={(e) => update("batch_analysis_id", e.target.value)}
              className={inputClass}
            >
              <option value="">Batch — not recorded</option>
              {batches.map((batch) => (
                <option key={batch.id} value={batch.id}>
                  {batch.batch_number}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
            >
              {busy ? "Adding…" : "Add study"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}

function StudyGrid({
  study,
  specification,
  onSaved,
  onRemove,
}: {
  study: StabilityStudy;
  specification: SpecificationTest[];
  onSaved: (study: StabilityStudy) => void;
  onRemove: (studyId: string) => void;
}) {
  /** Cell key -> value. The whole grid is ONE piece of state, because the
   * save is one request: the backend replaces the study's result set in a
   * single transaction, so a half-typed grid is never half-saved. */
  const [cells, setCells] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      study.results.map((r) => [cellKey(r.specification_test_id, r.timepoint_months), r.result]),
    ),
  );
  const [timepoints, setTimepoints] = useState<number[]>(() => {
    const recorded = [...new Set(study.results.map((r) => r.timepoint_months))];
    return recorded.length ? recorded.sort((a, b) => a - b) : DEFAULT_TIMEPOINTS;
  });
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const limits = useMemo(
    () => new Map(specification.map((test) => [test.id, test.acceptance_criterion])),
    [specification],
  );

  function setCell(testId: string, months: number, value: string) {
    setCells((previous) => ({ ...previous, [cellKey(testId, months)]: value }));
    setDirty(true);
  }

  function onPaste(event: React.ClipboardEvent) {
    const text = event.clipboardData.getData("text/plain");
    // A paste with no tab and no newline is one value going into one
    // cell -- the browser's own behaviour is right, so stay out of it.
    if (!text.includes("\t") && !text.includes("\n")) return;
    event.preventDefault();

    const mapping = mapPastedTable(parsePastedTable(text), specification);
    if (mapping.cells.length === 0) {
      setNote(
        "Nothing in that paste matched. The first row should hold the " +
          "timepoints and the first column the test names, spelled as they " +
          "are in the specification above.",
      );
      return;
    }

    setTimepoints((previous) =>
      [...new Set([...previous, ...mapping.timepoints])].sort((a, b) => a - b),
    );
    setCells((previous) => {
      const next = { ...previous };
      for (const cell of mapping.cells) {
        next[cellKey(cell.testId, cell.timepointMonths)] = cell.value;
      }
      return next;
    });
    setDirty(true);

    // Say what did NOT land, always. A paste that half-lands is worse than
    // one that visibly did not, because the half that landed looks
    // complete.
    const skipped = [
      ...mapping.unmatchedRows.map((row) => `test “${row}”`),
      ...mapping.unmatchedColumns.map((column) => `column “${column}”`),
    ];
    setNote(
      `Filled ${mapping.cells.length} cell(s).` +
        (skipped.length
          ? ` Not matched, and not entered: ${skipped.join(", ")}.`
          : ""),
    );
  }

  async function save() {
    setError(null);
    setSaving(true);
    try {
      const payload = [];
      for (const test of specification) {
        for (const months of timepoints) {
          const value = (cells[cellKey(test.id, months)] ?? "").trim();
          // An empty cell is not an empty result. A blank in a stability
          // table means "not tested at this timepoint", which the rendered
          // section states in words; storing "" would make it a reported
          // result of nothing.
          if (!value) continue;
          payload.push({
            specification_test_id: test.id,
            timepoint_months: months,
            result: value,
          });
        }
      }
      const results = await api.replaceStabilityResults(study.id, payload);
      onSaved({ ...study, results });
      setDirty(false);
      setNote(`Saved ${results.length} result(s).`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the results");
    } finally {
      setSaving(false);
    }
  }

  const failing = specification.some((test) =>
    timepoints.some((months) => {
      const value = (cells[cellKey(test.id, months)] ?? "").trim();
      return value ? evaluate(limits.get(test.id) ?? "", value) === false : false;
    }),
  );

  return (
    <div className="mb-3 rounded-md border border-slate-200 p-3 text-sm dark:border-slate-800">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium">
          {study.study_type} · {study.condition} · {study.duration_months} months
        </span>
        <button
          type="button"
          onClick={() => onRemove(study.id)}
          className="text-xs text-slate-500 hover:text-red-600"
        >
          Remove study
        </button>
      </div>

      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

      <p className="mb-2 text-xs text-slate-500">
        Paste a table straight from your spreadsheet — timepoints across the
        top, test names down the side. Anything that does not match a test in
        the specification is reported, never guessed at.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-left" onPaste={onPaste}>
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              <th className="py-1 pr-2">Test</th>
              {/* The limit sits between the test and the values, not on
                  another screen: a limit and the numbers judged against it
                  belong a centimetre apart. */}
              <th className="py-1 pr-2">Acceptance criterion</th>
              {timepoints.map((months) => (
                <th key={months} className="py-1 pr-2">
                  {months} mo
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* Driven by the SPECIFICATION, so every test it declares gets a
                row and an untested one is visible as a gap rather than
                being absent from the screen. */}
            {specification.map((test) => (
              <tr key={test.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1 pr-2">{test.test_name}</td>
                <td className="py-1 pr-2 text-slate-600 dark:text-slate-400">
                  {test.acceptance_criterion}
                </td>
                {timepoints.map((months) => {
                  const value = cells[cellKey(test.id, months)] ?? "";
                  const verdict = value.trim()
                    ? evaluate(test.acceptance_criterion, value)
                    : null;
                  return (
                    <td key={months} className="py-1 pr-2">
                      <input
                        aria-label={`${test.test_name} at ${months} months`}
                        value={value}
                        onChange={(e) => setCell(test.id, months, e.target.value)}
                        className={`${inputClass} ${cellClass(verdict, !value.trim())}`}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Flagged the moment it is typed, which is the point: the person
          entering this has the stability report in front of them and can
          check a transposed digit in five seconds. The same finding at
          export, days later, is a hunt. */}
      {failing && (
        <p className="mt-2 text-sm font-medium text-red-600">
          At least one result is outside its acceptance criterion. Inside the
          claimed shelf life that blocks the export (rule R23) — check the
          value against the report before saving.
        </p>
      )}
      {note && <p className="mt-2 text-xs text-slate-500">{note}</p>}

      <div className="mt-2 flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving || !dirty}
          className="rounded-md bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
        >
          {saving ? "Saving…" : "Save this table"}
        </button>
        {dirty && (
          <span className="text-xs text-amber-700 dark:text-amber-400">
            Unsaved changes
          </span>
        )}
      </div>
    </div>
  );
}
