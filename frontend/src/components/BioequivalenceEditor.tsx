"use client";

/**
 * Bioequivalence study entry (5.3.1.2, and the 1.4.1 / 5.2 documents built
 * from it).
 *
 * ## Why this is not the generic add-a-row form
 *
 * The wizard's other steps are lists of field specs rendered by one shared
 * component, and that shape has paid off seven times over. Two things here
 * do not fit it, and both are about what the data IS:
 *
 *   1. **The comparator is a row that other rows point at.** A study names
 *      a `ReferenceProduct` by foreign key -- deliberately, so 1.2, 2.3,
 *      1.4.1 and 5.2 cannot each hold their own copy of the brand and
 *      drift. Entering it as a free-text field on the study would put the
 *      drift straight back, which is what rule R26 exists to catch.
 *   2. **The results are a fixed three-row table, not a list.** Cmax,
 *      AUC(0-t) and AUC(0-inf) are transcribed off one page of the CRO's
 *      report together. A study holding two of its three intervals is
 *      worse than one holding none, because it looks answered -- so they
 *      are entered as a table and saved as a set (PUT, not three POSTs).
 *
 * ## Why the verdict appears as you type
 *
 * The same claim P20's batch screen makes, and it is stronger here. The
 * filer has the report open in front of them; a transposed digit in a
 * confidence interval takes five seconds to check now and is a hunt three
 * days later at export. The check is `src/lib/be-window.ts`, it is
 * ADVISORY, and rule R25 on the backend is the gate -- see that module's
 * docstring on why this particular duplication is acceptable.
 *
 * The window itself is not hard-coded here: it comes from the product's
 * `narrow_therapeutic_index` flag, which is what the backend's region
 * profile keys `window_for` on.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "@/lib/api";
import {
  describeWindow,
  outsideBounds,
  parseBound,
  verdictFor,
  windowFor,
  type AcceptanceWindow,
} from "@/lib/be-window";
import {
  PK_PARAMETERS,
  type BatchAnalysis,
  type BioequivalenceStudy,
  type PKParameter,
  type ReferenceProduct,
} from "@/lib/types";
import { Card, ErrorNotice } from "@/components/ui";

const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm " +
  "dark:border-slate-700 dark:bg-slate-900";

const buttonClass =
  "rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium " +
  "hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800";

/** One editable row of the results table. Held as STRINGS, not numbers:
 * the box is mid-edit for most of its life ("9", "95.", "95.8"), and
 * coercing to a number on every keystroke turns a half-typed bound into a
 * value the verdict would judge. Parsing happens at the edge. */
interface ResultDraft {
  parameter: PKParameter;
  geometric_mean_ratio: string;
  ci_lower: string;
  ci_upper: string;
  intra_subject_cv: string;
}

function resultsOf(study: BioequivalenceStudy): ResultDraft[] {
  // Always all three rows, in the order every report prints them, whether
  // or not the study has an answer for each: a table that hides the
  // parameters nobody has filled in is a table that cannot be used to
  // notice they are missing.
  return PK_PARAMETERS.map((parameter) => {
    const saved = study.results.find((r) => r.parameter === parameter);
    return {
      parameter,
      geometric_mean_ratio: saved?.geometric_mean_ratio ?? "",
      ci_lower: saved?.ci_lower ?? "",
      ci_upper: saved?.ci_upper ?? "",
      intra_subject_cv: saved?.intra_subject_cv ?? "",
    };
  });
}

export function BioequivalenceEditor({
  productId,
  narrowTherapeuticIndex = false,
}: {
  productId: string;
  /** Which of the two acceptance windows this molecule is judged against.
   * Comes from the product, because it is a property of the drug -- the
   * region owns the pair of windows, the product owns which applies. */
  narrowTherapeuticIndex?: boolean;
}) {
  const [studies, setStudies] = useState<BioequivalenceStudy[]>([]);
  const [comparators, setComparators] = useState<ReferenceProduct[]>([]);
  const [batches, setBatches] = useState<BatchAnalysis[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const acceptanceWindow = useMemo(
    () => windowFor(narrowTherapeuticIndex),
    [narrowTherapeuticIndex],
  );

  const reload = useCallback(async () => {
    try {
      const [loadedStudies, loadedComparators, loadedBatches] = await Promise.all([
        api.listBioequivalenceStudies(productId),
        api.listReferenceProducts(productId),
        // The test batch is offered from the batches 3.2.P.5.4 already
        // files, never typed: an assessor cross-references that batch
        // number between Module 5 and Module 3, and a free-text box here
        // is how the two sections come to name different material.
        api.listBatches("drug-product", productId),
      ]);
      setStudies(loadedStudies);
      setComparators(loadedComparators);
      setBatches(loadedBatches);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the studies");
    }
  }, [productId]);

  // WHY the initial load is written out here rather than `void reload()`:
  // calling a setState-ing function synchronously in an effect body
  // triggers cascading renders, and the lint rule that says so is right.
  // setState belongs in the promise's callback. The `cancelled` flag is
  // the same guard SpecificationEditor and StabilityGrid use -- a product
  // switched before the fetch lands must not write the old one's rows
  // into the new one's screen.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.listBioequivalenceStudies(productId),
      api.listReferenceProducts(productId),
      api.listBatches("drug-product", productId),
    ])
      .then(([loadedStudies, loadedComparators, loadedBatches]) => {
        if (cancelled) return;
        setStudies(loadedStudies);
        setComparators(loadedComparators);
        setBatches(loadedBatches);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load the studies");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [productId]);

  const addComparator = useCallback(
    async (payload: Record<string, unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await api.createProductChild(productId, "reference-products", payload);
        await reload();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not save the comparator");
      } finally {
        setBusy(false);
      }
    },
    [productId, reload],
  );

  const addStudy = useCallback(
    async (payload: Record<string, unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await api.createProductChild(productId, "bioequivalence", payload);
        await reload();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not save the study");
      } finally {
        setBusy(false);
      }
    },
    [productId, reload],
  );

  const removeStudy = useCallback(
    async (studyId: string) => {
      try {
        await api.deleteProductChild(productId, "bioequivalence", studyId);
        await reload();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not remove the study");
      }
    },
    [productId, reload],
  );

  return (
    <div className="space-y-4">
      {error && <ErrorNotice message={error} />}

      <Card>
        <h3 className="text-sm font-semibold">Reference product</h3>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
          The comparator, as a record rather than a name: an assessor checks that
          the batch was in date when it was dosed, and that the brand is the one
          your application claims equivalence to. Every study points at one of
          these, so 1.2, 2.3, 1.4.1 and 5.2 cannot name different products.
        </p>
        <ComparatorList comparators={comparators} />
        <ComparatorForm busy={busy} onAdd={addComparator} />
      </Card>

      <Card>
        <h3 className="text-sm font-semibold">Bioequivalence study</h3>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
          Acceptance window for this product:{" "}
          <span className="font-mono">{describeWindow(acceptanceWindow)}</span>
          {narrowTherapeuticIndex
            ? " — the narrow-therapeutic-index window."
            : " — the ordinary ICH/WHO window."}
        </p>
        <StudyForm
          busy={busy}
          comparators={comparators}
          batches={batches}
          onAdd={addStudy}
        />
      </Card>

      {studies.map((study) => (
        <Card key={study.id}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">{study.study_identifier}</h3>
              <p className="text-xs text-slate-600 dark:text-slate-400">
                {study.design_summary}
                {study.subjects_enrolled !== null && (
                  <>
                    {" · "}
                    {study.subjects_enrolled} enrolled
                    {study.dropouts ? `, ${study.dropouts} withdrew` : ""}
                  </>
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void removeStudy(study.id)}
              className="text-xs text-slate-500 hover:text-red-600"
            >
              Remove
            </button>
          </div>
          {/* Keyed by the study, so switching studies REMOUNTS the grid
              rather than leaving one study's draft rows on another's
              screen -- which is what the effect this replaces used to do,
              at the cost of a cascading render. */}
          <ResultsGrid
            key={study.id}
            study={study}
            acceptanceWindow={acceptanceWindow}
            onSaved={reload}
          />
        </Card>
      ))}
    </div>
  );
}

function ComparatorList({ comparators }: { comparators: ReferenceProduct[] }) {
  if (comparators.length === 0) return null;
  return (
    <ul className="mt-3 space-y-1 text-sm">
      {comparators.map((comparator) => (
        <li
          key={comparator.id}
          className="rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800"
        >
          <span className="font-medium">{comparator.identity}</span>
          <span className="text-xs text-slate-500">
            {comparator.batch_number ? ` · batch ${comparator.batch_number}` : ""}
            {comparator.expiry_date ? ` · expires ${comparator.expiry_date}` : ""}
            {comparator.country_of_origin ? ` · ${comparator.country_of_origin}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ComparatorForm({
  busy,
  onAdd,
}: {
  busy: boolean;
  onAdd: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});

  const set = (name: string, value: string) =>
    setDraft((previous) => ({ ...previous, [name]: value }));

  return (
    <form
      className="mt-3 space-y-2"
      onSubmit={async (event) => {
        event.preventDefault();
        // Empty strings become null rather than "": a blank box means the
        // fact is not on file, and "" would render as a present-but-empty
        // value on the BTI form instead of the [[NOT YET ON FILE]] marker
        // the rest of the platform uses.
        const payload = Object.fromEntries(
          Object.entries(draft).map(([key, value]) => [key, value.trim() || null]),
        );
        await onAdd(payload);
        setDraft({});
      }}
    >
      <div className="grid gap-2 sm:grid-cols-3">
        <LabelledInput
          label="Brand name"
          required
          value={draft.name ?? ""}
          onChange={(v) => set("name", v)}
          placeholder="Amoxil 500 mg capsules"
        />
        <LabelledInput
          label="Manufacturer"
          value={draft.manufacturer ?? ""}
          onChange={(v) => set("manufacturer", v)}
        />
        <LabelledInput
          label="Strength"
          value={draft.strength ?? ""}
          onChange={(v) => set("strength", v)}
        />
        <LabelledInput
          label="Country of origin"
          value={draft.country_of_origin ?? ""}
          onChange={(v) => set("country_of_origin", v)}
          help="Agencies expect the innovator as marketed in a reference market."
        />
        <LabelledInput
          label="Batch number"
          value={draft.batch_number ?? ""}
          onChange={(v) => set("batch_number", v)}
        />
        <LabelledInput
          label="Expiry date"
          type="date"
          value={draft.expiry_date ?? ""}
          onChange={(v) => set("expiry_date", v)}
          help="Checked against the study period — a comparator dosed after expiry invalidates the study."
        />
      </div>
      <button type="submit" disabled={busy || !draft.name} className={buttonClass}>
        Add reference product
      </button>
    </form>
  );
}

function StudyForm({
  busy,
  comparators,
  batches,
  onAdd,
}: {
  busy: boolean;
  comparators: ReferenceProduct[];
  batches: BatchAnalysis[];
  onAdd: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({
    design: "crossover",
    fed_state: "fasting",
    dose_regimen: "single dose",
  });

  const set = (name: string, value: string) =>
    setDraft((previous) => ({ ...previous, [name]: value }));

  return (
    <form
      className="mt-3 space-y-2"
      onSubmit={async (event) => {
        event.preventDefault();
        const numeric = new Set([
          "subjects_enrolled",
          "subjects_completed",
          "test_batch_size_units",
        ]);
        const payload = Object.fromEntries(
          Object.entries(draft).map(([key, value]) => {
            const trimmed = value.trim();
            if (trimmed === "") return [key, null];
            return [key, numeric.has(key) ? Number(trimmed) : trimmed];
          }),
        );
        await onAdd(payload);
        setDraft({ design: "crossover", fed_state: "fasting", dose_regimen: "single dose" });
      }}
    >
      <div className="grid gap-2 sm:grid-cols-3">
        <LabelledInput
          label="Study number"
          required
          value={draft.study_identifier ?? ""}
          onChange={(v) => set("study_identifier", v)}
          placeholder="LAMOX/BE/2025-01"
          help="The CRO's protocol number. It ties 1.4.1, 5.2 and the report at 5.3.1.2 together."
        />
        <LabelledSelect
          label="Design"
          value={draft.design ?? ""}
          onChange={(v) => set("design", v)}
          options={["crossover", "parallel", "replicate crossover"]}
        />
        <LabelledSelect
          label="Fed state"
          value={draft.fed_state ?? ""}
          onChange={(v) => set("fed_state", v)}
          options={["fasting", "fed"]}
        />
        <LabelledSelect
          label="Dose regimen"
          value={draft.dose_regimen ?? ""}
          onChange={(v) => set("dose_regimen", v)}
          options={["single dose", "multiple dose"]}
        />
        <LabelledInput
          label="Subjects enrolled"
          type="number"
          value={draft.subjects_enrolled ?? ""}
          onChange={(v) => set("subjects_enrolled", v)}
        />
        <LabelledInput
          label="Subjects completed"
          type="number"
          value={draft.subjects_completed ?? ""}
          onChange={(v) => set("subjects_completed", v)}
          help="Dropouts are what an assessor checks the study's power against."
        />
        <LabelledInput
          label="Analyte"
          value={draft.analyte ?? ""}
          onChange={(v) => set("analyte", v)}
          placeholder="Amoxicillin in human plasma"
        />
        <LabelledInput
          label="CRO"
          value={draft.cro_name ?? ""}
          onChange={(v) => set("cro_name", v)}
        />
        <LabelledInput
          label="Study site"
          value={draft.study_site ?? ""}
          onChange={(v) => set("study_site", v)}
        />
        <LabelledSelect
          label="Reference product"
          value={draft.reference_product_id ?? ""}
          onChange={(v) => set("reference_product_id", v)}
          options={comparators.map((c) => ({ value: c.id, label: c.identity }))}
          placeholder="— pick a comparator —"
        />
        <LabelledSelect
          label="Test batch"
          value={draft.test_batch_id ?? ""}
          onChange={(v) => set("test_batch_id", v)}
          options={batches.map((b) => ({ value: b.id, label: b.batch_number }))}
          placeholder="— pick a batch from 3.2.P.5.4 —"
          help="A foreign key, not a typed batch number: Module 5 and 3.2.P.5.4 must name the same material."
        />
        <LabelledInput
          label="Test batch size (units)"
          type="number"
          value={draft.test_batch_size_units ?? ""}
          onChange={(v) => set("test_batch_size_units", v)}
          help="Checked against the commercial batch in 3.2.P.3.2 (rule R27): at least a tenth of it, or 100 000 units."
        />
      </div>
      <button
        type="submit"
        disabled={busy || !draft.study_identifier}
        className={buttonClass}
      >
        Add bioequivalence study
      </button>
    </form>
  );
}

/**
 * The three intervals, with the verdict beside each as it is typed.
 *
 * Saved as a SET: the whole table goes up in one PUT, so the study cannot
 * end up holding two of its three parameters.
 */
function ResultsGrid({
  study,
  acceptanceWindow,
  onSaved,
}: {
  study: BioequivalenceStudy;
  acceptanceWindow: AcceptanceWindow;
  onSaved: () => Promise<void>;
}) {
  // Initialised ONCE from the study, and never re-synchronised by an
  // effect. Two things replace that effect, and both are better:
  //
  //   * after a save, the rows come from the PUT's own response (below),
  //     so what the screen shows is what the server stored -- including
  //     any normalisation the client would otherwise miss;
  //   * a DIFFERENT study is a different component, keyed by id in the
  //     parent, so React remounts it rather than this reconciling.
  //
  // Calling setState synchronously in an effect to mirror a prop is the
  // cascading-render pattern React documents against, and the lint rule
  // that flags it is right.
  const [rows, setRows] = useState<ResultDraft[]>(() => resultsOf(study));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (parameter: PKParameter, field: keyof ResultDraft, value: string) =>
    setRows((previous) =>
      previous.map((row) => (row.parameter === parameter ? { ...row, [field]: value } : row)),
    );

  async function save() {
    setSaving(true);
    setError(null);
    try {
      // A row with neither bound typed is not sent at all -- it is a
      // parameter this study has not reported, and sending "" would be
      // sending a confidence interval of nothing.
      const payload = rows
        .filter((row) => row.ci_lower.trim() !== "" && row.ci_upper.trim() !== "")
        .map((row) => ({
          parameter: row.parameter,
          geometric_mean_ratio: row.geometric_mean_ratio.trim() || null,
          ci_lower: row.ci_lower.trim(),
          ci_upper: row.ci_upper.trim(),
          intra_subject_cv: row.intra_subject_cv.trim() || null,
        }));
      const stored = await api.replaceBioequivalenceResults(study.id, payload);
      // The server's answer, not the draft that was sent: it is the row
      // 1.4.1 and 5.2 will render from, so it is the row the screen should
      // show.
      setRows(resultsOf({ ...study, results: stored }));
      await onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the results");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-3 space-y-2">
      {error && <ErrorNotice message={error} />}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-slate-500">
              <th className="py-1 pr-2">Parameter</th>
              <th className="py-1 pr-2">Ratio (%)</th>
              <th className="py-1 pr-2">90 % CI lower</th>
              <th className="py-1 pr-2">90 % CI upper</th>
              <th className="py-1 pr-2">Intra-subject CV (%)</th>
              <th className="py-1">Against {describeWindow(acceptanceWindow)}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const lower = parseBound(row.ci_lower);
              const upper = parseBound(row.ci_upper);
              const verdict = verdictFor(lower, upper, acceptanceWindow);
              const breached = outsideBounds(lower, upper, acceptanceWindow);
              return (
                <tr key={row.parameter} className="border-t border-slate-200 dark:border-slate-800">
                  <td className="py-1 pr-2 font-mono text-xs">{row.parameter}</td>
                  <td className="py-1 pr-2">
                    <input
                      className={inputClass}
                      value={row.geometric_mean_ratio}
                      onChange={(e) =>
                        set(row.parameter, "geometric_mean_ratio", e.target.value)
                      }
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <input
                      className={inputClass}
                      value={row.ci_lower}
                      onChange={(e) => set(row.parameter, "ci_lower", e.target.value)}
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <input
                      className={inputClass}
                      value={row.ci_upper}
                      onChange={(e) => set(row.parameter, "ci_upper", e.target.value)}
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <input
                      className={inputClass}
                      value={row.intra_subject_cv}
                      onChange={(e) => set(row.parameter, "intra_subject_cv", e.target.value)}
                    />
                  </td>
                  <td className="py-1 text-xs">
                    {/* Three states, and the third is not a pass. An
                        interval nobody has finished typing says nothing,
                        and colouring it red would teach the filer to
                        ignore the colour. */}
                    {verdict === null && (
                      <span className="text-slate-500">not reported</span>
                    )}
                    {verdict === "within" && (
                      <span className="text-emerald-700 dark:text-emerald-400">within</span>
                    )}
                    {verdict === "outside" && (
                      <span className="font-medium text-red-600">
                        OUTSIDE ({breached.join(" and ")} bound)
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3">
        <button type="button" onClick={save} disabled={saving} className={buttonClass}>
          {saving ? "Saving…" : "Save results"}
        </button>
        <span className="text-xs text-slate-500">
          Rule R25 blocks the export on an interval outside the window; this check is
          advisory and only tells you sooner.
        </span>
      </div>
    </div>
  );
}

function LabelledInput({
  label,
  value,
  onChange,
  type = "text",
  required = false,
  placeholder,
  help,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
  help?: string;
}) {
  return (
    <label className="block text-xs">
      <span className="text-slate-600 dark:text-slate-400">
        {label}
        {required && " *"}
      </span>
      <input
        className={`${inputClass} mt-1`}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      {help && <span className="mt-1 block text-slate-500">{help}</span>}
    </label>
  );
}

function LabelledSelect({
  label,
  value,
  onChange,
  options,
  placeholder,
  help,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<string | { value: string; label: string }>;
  placeholder?: string;
  help?: string;
}) {
  return (
    <label className="block text-xs">
      <span className="text-slate-600 dark:text-slate-400">{label}</span>
      <select
        className={`${inputClass} mt-1`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((option) => {
          const item = typeof option === "string" ? { value: option, label: option } : option;
          return (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          );
        })}
      </select>
      {help && <span className="mt-1 block text-slate-500">{help}</span>}
    </label>
  );
}
