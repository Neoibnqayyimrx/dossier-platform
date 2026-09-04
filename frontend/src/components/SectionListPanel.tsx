"use client";

/**
 * What this dossier owes, and the questions only the filer can answer (P17).
 *
 * WHY this screen matters more than it looks: until now "what is still
 * missing from this dossier?" was answerable only by running a script in a
 * terminal. The person who actually needs that answer — the regulatory
 * affairs officer assembling the filing — has no terminal. This is the same
 * resolution the package builder uses, drawn.
 *
 * Nothing here hard-codes the section list, the module names, or which
 * leaves are conditional. All of it arrives from GET
 * /projects/{id}/section-status, for the reason /enums and /regions already
 * exist: a second copy in TypeScript is a copy that drifts, and here it
 * would drift into telling a filer that a section they owe is excused.
 */

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { SectionStatus, SectionStatusValue } from "@/lib/types";
import { Badge, Card, ErrorNotice } from "@/components/ui";

const MODULE_TITLES: Record<number, string> = {
  1: "Module 1 — Administrative & product information",
  2: "Module 2 — Summaries",
  3: "Module 3 — Quality",
  4: "Module 4 — Nonclinical study reports",
  5: "Module 5 — Clinical study reports",
};

// Wording chosen so the four states cannot be read as a single "done / not
// done" axis. "Not applicable" is a FINISHED leaf — the platform files a
// cited statement for it — while "placeholder" is the opposite: something
// stands there, and it is not the document.
const STATUS_LABELS: Record<SectionStatusValue, string> = {
  produced: "produced",
  "not-applicable": "not applicable",
  placeholder: "placeholder",
  outstanding: "outstanding",
};

const STATUS_TONES: Record<SectionStatusValue, "good" | "bad" | "neutral"> = {
  produced: "good",
  "not-applicable": "good",
  placeholder: "bad",
  outstanding: "neutral",
};

function Counts({ sections }: { sections: SectionStatus[] }) {
  const tally = sections.reduce<Record<string, number>>((acc, section) => {
    acc[section.status] = (acc[section.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="flex flex-wrap gap-2">
      {(Object.keys(STATUS_LABELS) as SectionStatusValue[]).map((status) => (
        <Badge key={status} tone={STATUS_TONES[status]}>
          {tally[status] ?? 0} {STATUS_LABELS[status]}
        </Badge>
      ))}
      <Badge>{sections.length} leaves in total</Badge>
    </div>
  );
}

function ConditionControl({
  section,
  onAnswer,
  busy,
}: {
  section: SectionStatus;
  onAnswer: (answer: boolean | null) => void;
  busy: boolean;
}) {
  // Three buttons, not a checkbox: unanswered is a real, distinct state
  // (rule R19 warns about it), and a checkbox has no way to express it. A
  // default-unchecked box would silently answer "no" on the filer's behalf,
  // which is how a claim nobody made ends up in a dossier.
  const options: { label: string; value: boolean | null }[] = [
    { label: "Yes", value: true },
    { label: "No", value: false },
    { label: "Unanswered", value: null },
  ];

  return (
    <div className="mt-1 flex flex-wrap items-center gap-2">
      <p className="text-xs text-slate-500 dark:text-slate-400">
        {section.condition}
      </p>
      <div className="flex gap-1">
        {options.map((option) => (
          <button
            key={String(option.value)}
            type="button"
            disabled={busy}
            onClick={() => onAnswer(option.value)}
            className={`rounded-md border px-2 py-0.5 text-xs disabled:opacity-50 ${
              section.answer === option.value
                ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                : "border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SectionListPanel({
  projectId,
  onChanged,
}: {
  projectId: string;
  /** Answering a condition changes the readiness report (R19), so the page
   * has to refresh it — otherwise you answer a question and the warning you
   * just cleared is still on screen. */
  onChanged: () => void;
}) {
  const [sections, setSections] = useState<SectionStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .getSectionStatus(projectId)
      .then(setSections)
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Could not load the section list",
        ),
      );
  }, [projectId]);

  const answer = useCallback(
    async (number: string, value: boolean | null) => {
      setBusy(true);
      try {
        // The endpoint returns the whole recomputed list, so the answer and
        // its consequence (a statement leaf appearing or disappearing) land
        // on screen together rather than in two steps.
        setSections(await api.answerConditions(projectId, { [number]: value }));
        onChanged();
      } catch (err) {
        setError(
          err instanceof ApiError ? err.message : "Could not save that answer",
        );
      } finally {
        setBusy(false);
      }
    },
    [projectId, onChanged],
  );

  if (error) return <ErrorNotice message={error} />;
  if (!sections)
    return <p className="text-sm text-slate-500">Loading the section list…</p>;

  const modules = [...new Set(sections.map((s) => s.module))].sort();

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          What this dossier owes
        </h2>
        <Counts sections={sections} />
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
          A not-applicable section is not an absent one: it is filed as a
          statement citing the guideline that excuses it. Conditional sections
          are questions only you can answer — answering “no” files that
          statement, “yes” means the section owes real content.
        </p>
      </Card>

      {modules.map((module) => (
        <Card key={module}>
          <h3 className="mb-3 text-sm font-semibold">
            {MODULE_TITLES[module] ?? `Module ${module}`}
          </h3>
          <ul className="divide-y divide-slate-200 dark:divide-slate-800">
            {sections
              .filter((section) => section.module === module)
              .map((section) => (
                <li key={section.number} className="py-2">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-sm">
                      <span className="font-medium">{section.number}</span>{" "}
                      {section.title}
                    </span>
                    <Badge tone={STATUS_TONES[section.status]}>
                      {STATUS_LABELS[section.status]}
                    </Badge>
                  </div>
                  {section.citation && section.status === "not-applicable" && (
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      Basis: {section.citation}
                    </p>
                  )}
                  {section.applicability === "conditional" && (
                    <ConditionControl
                      section={section}
                      busy={busy}
                      onAnswer={(value) => answer(section.number, value)}
                    />
                  )}
                </li>
              ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}
