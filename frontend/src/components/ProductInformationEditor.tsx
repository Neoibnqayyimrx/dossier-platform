"use client";

/**
 * The product information step: the SmPC's authored sections, and the
 * derived ones shown as what they are (P23).
 *
 * ## Why this is a custom editor and not field specs
 *
 * The third deviation from `wizard-steps.ts`'s field-spec form, and the
 * first one that is not about tabular data. The reason here is that HALF
 * THE SCREEN IS NOT EDITABLE. Sections 1, 2, 3, 6.1, 6.3, 6.4 and 6.5 are
 * derived from the product, its packaging and its stability data, and this
 * screen's most important job is to show them WITH their provenance rather
 * than to collect them.
 *
 * A field spec describes an input. There is no honest way to spell "this
 * looks like section 6.3 of an SmPC, it says 24 months, and it is not
 * yours to type" as one.
 *
 * ## Why the derived block is shown at all
 *
 * An SmPC page that simply omitted section 6.3 would be baffling -- a
 * pharmacist would assume the platform had forgotten it and go looking for
 * somewhere to type. Showing it read-only, with a sentence saying where the
 * value comes from, turns a refusal into an explanation. That sentence is
 * `DerivedValue.source`, computed by the same backend function the three
 * documents render from, so it can never describe a value the documents do
 * not print.
 */

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type {
  DerivedValue,
  ProductInformationWrite,
  UndesirableEffect,
  Vocabularies,
} from "@/lib/types";
import { Badge, ErrorNotice } from "@/components/ui";

const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm " +
  "dark:border-slate-700 dark:bg-slate-900";

/**
 * The authored sections, in SmPC order, with the guideline's own numbering.
 *
 * The numbers are not decoration: an assessor's query arrives as "section
 * 4.4 does not mention renal impairment", and a form whose headings are
 * "Special warnings" instead of "4.4 Special warnings" makes the filer
 * translate. `blocking` marks the three that ARE the application -- rule
 * R30 refuses to export without them.
 */
const TEXT_SECTIONS: {
  name: keyof ProductInformationWrite;
  number: string;
  label: string;
  blocking?: boolean;
  help?: string;
}[] = [
  {
    name: "therapeutic_indications",
    number: "4.1",
    label: "Therapeutic indications",
    blocking: true,
    help: "What the medicine is authorised to treat. This is the claim the whole application is for, which is why it is typed here and never drafted by the model.",
  },
  {
    name: "posology_and_administration",
    number: "4.2",
    label: "Posology and method of administration",
    blocking: true,
  },
  { name: "interactions", number: "4.5", label: "Interaction with other medicinal products" },
  { name: "pregnancy_and_lactation", number: "4.6", label: "Fertility, pregnancy and lactation" },
  { name: "effects_on_driving", number: "4.7", label: "Effects on ability to drive" },
  { name: "overdose", number: "4.9", label: "Overdose" },
  { name: "incompatibilities", number: "6.2", label: "Incompatibilities" },
  {
    name: "special_precautions_for_disposal",
    number: "6.6",
    label: "Special precautions for disposal",
  },
];

/** The text sections that belong in each run, named by their SmPC number
 * rather than sliced by index. `slice(6)` silently dropped 4.9 Overdose
 * when 4.8 was inserted between the runs -- an off-by-one that produces a
 * form missing a section rather than an error. */
function sections(...numbers: string[]) {
  return numbers.map((number) => {
    const found = TEXT_SECTIONS.find((section) => section.number === number);
    if (!found) throw new Error(`No SmPC section ${number} in TEXT_SECTIONS`);
    return found;
  });
}

const EMPTY: ProductInformationWrite = {
  therapeutic_indications: null,
  posology_and_administration: null,
  contraindications: [],
  special_warnings: [],
  interactions: null,
  pregnancy_and_lactation: null,
  effects_on_driving: null,
  undesirable_effects: [],
  overdose: null,
  incompatibilities: null,
  special_precautions_for_disposal: null,
};

/**
 * One derived value, shown as a fact with a source rather than a disabled
 * input.
 *
 * WHY not `<input disabled>`: a greyed-out box still reads as "a field you
 * are not allowed to use right now", and a filer's next move is to look
 * for the permission. Rendering it as text with a provenance line says
 * something different -- this is not a field at all, it lives over there.
 */
function DerivedRow({ value }: { value: DerivedValue }) {
  return (
    <div className="border-b border-slate-100 py-2 last:border-0 dark:border-slate-800">
      <div className="flex flex-wrap items-baseline gap-2">
        {value.smpc_section && (
          <span className="font-mono text-xs text-slate-400">{value.smpc_section}</span>
        )}
        <span className="text-sm font-medium">{value.label}</span>
        <Badge tone="neutral">derived</Badge>
      </div>
      <p className="mt-0.5 text-sm">{value.value}</p>
      <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{value.source}</p>
    </div>
  );
}

/** A list section (4.3 contraindications, 4.4 warnings): one entry per
 * line, because both the SmPC and the leaflet print them as bullets and
 * rule R32 names an individual entry the leaflet's prose lost. */
function ListSection({
  number,
  label,
  help,
  blocking,
  entries,
  onChange,
}: {
  number: string;
  label: string;
  help: string;
  blocking?: boolean;
  entries: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-baseline gap-2">
        <span className="font-mono text-xs text-slate-400">{number}</span>
        <label className="text-sm font-medium">{label}</label>
        {blocking && <Badge tone="bad">required</Badge>}
      </div>
      <textarea
        className={`${inputClass} min-h-24 font-sans`}
        value={entries.join("\n")}
        // Split on newline, not on comma: these sentences contain commas,
        // and a filer pasting three contraindications out of a reference
        // SmPC pastes them as lines.
        onChange={(e) => onChange(e.target.value.split("\n"))}
        placeholder="One per line"
      />
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{help}</p>
    </div>
  );
}

export function ProductInformationEditor({
  productId,
  vocabularies,
}: {
  productId: string;
  vocabularies: Vocabularies;
}) {
  const [draft, setDraft] = useState<ProductInformationWrite>(EMPTY);
  const [derived, setDerived] = useState<DerivedValue[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  // The house pattern for a fetch-on-mount (SpecificationEditor,
  // BioequivalenceEditor): an inline promise chain guarded by `cancelled`,
  // so a slow response cannot land on a screen that has moved on.
  useEffect(() => {
    let cancelled = false;
    api
      .getProductInformation(productId)
      .then((body) => {
        if (cancelled) return;
        setDerived(body.derived);
        setDraft({
          therapeutic_indications: body.therapeutic_indications,
          posology_and_administration: body.posology_and_administration,
          contraindications: body.contraindications,
          special_warnings: body.special_warnings,
          interactions: body.interactions,
          pregnancy_and_lactation: body.pregnancy_and_lactation,
          effects_on_driving: body.effects_on_driving,
          undesirable_effects: body.undesirable_effects,
          overdose: body.overdose,
          incompatibilities: body.incompatibilities,
          special_precautions_for_disposal: body.special_precautions_for_disposal,
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // A 404 is the ORDINARY state of a product whose SmPC has not been
        // started, not a failure -- so it leaves the empty form in place.
        // Only a real error becomes an error.
        if (err instanceof ApiError && err.status === 404) return;
        setError(err instanceof ApiError ? err.message : "Could not load");
      });
    return () => {
      cancelled = true;
    };
  }, [productId]);

  function update<K extends keyof ProductInformationWrite>(
    name: K,
    value: ProductInformationWrite[K],
  ) {
    setSaved(false);
    setDraft((previous) => ({ ...previous, [name]: value }));
  }

  async function save() {
    setError(null);
    setBusy(true);
    try {
      const body = await api.saveProductInformation(productId, {
        ...draft,
        // Blank lines are dropped on the server too (an empty bullet in a
        // patient leaflet is not something a template can render around),
        // but trimming here means the filer sees what was saved.
        contraindications: draft.contraindications.filter((e) => e.trim()),
        special_warnings: draft.special_warnings.filter((e) => e.trim()),
        undesirable_effects: draft.undesirable_effects.filter((e) => e.effect.trim()),
      });
      setDerived(body.derived);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  const frequencies = vocabularies.adverse_event_frequency ?? [];

  function updateEffect(index: number, patch: Partial<UndesirableEffect>) {
    update(
      "undesirable_effects",
      draft.undesirable_effects.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  }

  return (
    <div className="space-y-6">
      {error && <ErrorNotice message={error} />}

      <section className="rounded-md border border-slate-200 p-4 dark:border-slate-800">
        <h3 className="text-sm font-semibold">Derived from data you have already entered</h3>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          These are printed in the SmPC, on the label and in the patient leaflet — all
          three read them from one place, so they cannot disagree. To change one, change
          it where it lives.
        </p>
        <div className="mt-3">
          {derived.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Save this step once to see what the three documents will print.
            </p>
          ) : (
            derived.map((value) => <DerivedRow key={value.field} value={value} />)
          )}
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Clinical particulars (SmPC section 4)</h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            These exist nowhere else in the dossier, so they are typed rather than
            derived — and they are never drafted by the model: an indication, a dose and
            a contraindication are regulatory claims.
          </p>
        </div>

        {sections("4.1", "4.2").map((section) => (
          <div key={section.name}>
            <div className="mb-1 flex flex-wrap items-baseline gap-2">
              <span className="font-mono text-xs text-slate-400">{section.number}</span>
              <label className="text-sm font-medium">{section.label}</label>
              {section.blocking && <Badge tone="bad">required</Badge>}
            </div>
            <textarea
              className={`${inputClass} min-h-24`}
              value={(draft[section.name] as string | null) ?? ""}
              onChange={(e) => update(section.name, e.target.value || null)}
            />
            {section.help && (
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{section.help}</p>
            )}
          </div>
        ))}

        <ListSection
          number="4.3"
          label="Contraindications"
          blocking
          entries={draft.contraindications}
          onChange={(next) => update("contraindications", next)}
          help="Printed as bullets in the SmPC and, in the same words, in the leaflet's “do not take this medicine if” list. Write them as a patient would read them — the leaflet carries them verbatim."
        />
        <ListSection
          number="4.4"
          label="Special warnings and precautions for use"
          entries={draft.special_warnings}
          onChange={(next) => update("special_warnings", next)}
          help="Shared with the leaflet's “talk to your doctor before taking this medicine if” list."
        />

        {sections("4.5", "4.6", "4.7").map((section) => (
          <div key={section.name}>
            <div className="mb-1 flex items-baseline gap-2">
              <span className="font-mono text-xs text-slate-400">{section.number}</span>
              <label className="text-sm font-medium">{section.label}</label>
            </div>
            <textarea
              className={`${inputClass} min-h-20`}
              value={(draft[section.name] as string | null) ?? ""}
              onChange={(e) => update(section.name, e.target.value || null)}
            />
          </div>
        ))}

        <div>
          <div className="mb-1 flex items-baseline gap-2">
            <span className="font-mono text-xs text-slate-400">4.8</span>
            <label className="text-sm font-medium">Undesirable effects</label>
          </div>
          <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
            The frequency is a CIOMS band, not free text: both the SmPC and the leaflet
            print these grouped by band and in band order, and “fairly often” cannot be
            ordered.
          </p>
          <div className="space-y-2">
            {draft.undesirable_effects.map((row, index) => (
              <div key={index} className="flex gap-2">
                <input
                  className={inputClass}
                  value={row.effect}
                  placeholder="Diarrhoea"
                  onChange={(e) => updateEffect(index, { effect: e.target.value })}
                />
                <select
                  className={`${inputClass} max-w-64`}
                  value={row.frequency}
                  onChange={(e) => updateEffect(index, { frequency: e.target.value })}
                >
                  {frequencies.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="text-xs text-slate-500 hover:text-red-600"
                  onClick={() =>
                    update(
                      "undesirable_effects",
                      draft.undesirable_effects.filter((_, i) => i !== index),
                    )
                  }
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            className="mt-2 rounded-md border border-slate-300 px-3 py-1 text-xs dark:border-slate-700"
            onClick={() =>
              update("undesirable_effects", [
                ...draft.undesirable_effects,
                { effect: "", frequency: frequencies[0]?.value ?? "" },
              ])
            }
            disabled={frequencies.length === 0}
          >
            Add side effect
          </button>
        </div>

        {sections("4.9", "6.2", "6.6").map((section) => (
          <div key={section.name}>
            <div className="mb-1 flex items-baseline gap-2">
              <span className="font-mono text-xs text-slate-400">{section.number}</span>
              <label className="text-sm font-medium">{section.label}</label>
            </div>
            <textarea
              className={`${inputClass} min-h-20`}
              value={(draft[section.name] as string | null) ?? ""}
              onChange={(e) => update(section.name, e.target.value || null)}
            />
          </div>
        ))}
      </section>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={busy}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
        >
          {busy ? "Saving..." : "Save product information"}
        </button>
        {saved && <span className="text-xs text-emerald-700 dark:text-emerald-400">Saved</span>}
      </div>
    </div>
  );
}
