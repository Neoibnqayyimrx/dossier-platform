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
import type {
  SectionDocument,
  SectionStatus,
  SectionStatusValue,
} from "@/lib/types";
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

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Attach the real paper to one leaf (P18).
 *
 * WHY the filename and upload date are shown rather than just a tick: the
 * person assembling a submission needs to recognise their own file — "is
 * that the CPP we got in March, or the expired one?" is the question a
 * green tick cannot answer. The section title is what the leaf IS; the
 * filename is how a human knows which document they attached.
 */
function DocumentControl({
  sectionNumber,
  document,
  busy,
  onUpload,
  onRemove,
}: {
  sectionNumber: string;
  document: SectionDocument | undefined;
  busy: boolean;
  onUpload: (file: File) => void;
  onRemove: () => void;
}) {
  // Derived from the leaf, not generated: a random id is impure in render
  // (React can call a component twice), and the leaf number is already the
  // unique thing this control belongs to.
  const inputId = `upload-${sectionNumber}`;

  if (document) {
    return (
      <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
        <span className="font-medium text-slate-700 dark:text-slate-300">
          {document.original_filename}
        </span>
        <span>{humanSize(document.size_bytes)}</span>
        <span>attached {new Date(document.uploaded_at).toLocaleDateString()}</span>
        <label className="cursor-pointer underline hover:text-slate-800 dark:hover:text-slate-200">
          replace
          <input
            type="file"
            className="hidden"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUpload(file);
              event.target.value = "";
            }}
          />
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={onRemove}
          className="underline hover:text-red-600 disabled:opacity-50"
        >
          remove
        </button>
      </div>
    );
  }

  return (
    <div className="mt-1">
      <label
        htmlFor={inputId}
        className="cursor-pointer text-xs text-slate-500 underline hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
      >
        {busy ? "Uploading…" : "Attach a PDF or .docx"}
      </label>
      <input
        id={inputId}
        type="file"
        className="hidden"
        disabled={busy}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onUpload(file);
          event.target.value = "";
        }}
      />
    </div>
  );
}

/**
 * The copies a repeated section owes (P19).
 *
 * WHY the copies are listed rather than counted: "2 copies" tells the filer
 * how much work there is, and "Ampicillin / Cloxacillin" tells them what
 * the work IS. The subject names are the same strings that end up in the
 * folder names and the eCTD backbone, so what the screen shows and what the
 * package contains are one list.
 */
function Copies({ section }: { section: SectionStatus }) {
  return (
    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
      {section.copies.length}{" "}
      {section.copies.length === 1 ? "copy" : "copies"} — one per{" "}
      {section.repeat?.replace(/_/g, " ")}:{" "}
      {section.copies.map((copy) => copy.subject).join(", ")}
    </p>
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
  const [documents, setDocuments] = useState<SectionDocument[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [onlyMissing, setOnlyMissing] = useState(false);

  const load = useCallback(() => {
    Promise.all([api.getSectionStatus(projectId), api.listDocuments(projectId)])
      .then(([status, docs]) => {
        setSections(status);
        setDocuments(docs);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Could not load the section list",
        ),
      );
  }, [projectId]);

  useEffect(load, [load]);

  const documentsByLeaf = new Map(
    documents.map((d) => [
      d.subject_slug ? `${d.section_number}-${d.subject_slug}` : d.section_number,
      d,
    ]),
  );

  const upload = useCallback(
    async (section: SectionStatus, file: File) => {
      setBusy(true);
      setError(null);
      try {
        await api.uploadDocument(projectId, section.number, file);
        load();
        // An attached document can clear rule R20, which is an export
        // blocker -- so the readiness verdict on the page is now stale.
        onChanged();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not attach that file");
      } finally {
        setBusy(false);
      }
    },
    [projectId, load, onChanged],
  );

  const remove = useCallback(
    async (section: SectionStatus) => {
      setBusy(true);
      try {
        await api.deleteDocument(projectId, section.number);
        load();
        onChanged();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not remove that file");
      } finally {
        setBusy(false);
      }
    },
    [projectId, load, onChanged],
  );

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

  // "What's still missing": every leaf that owes a document and has none.
  // WHY this is a filter on the same list rather than a separate screen:
  // the checklist and the section list are the same question asked with
  // different patience, and two screens would be two things to keep in
  // step. It is the view the person assembling a submission keeps open.
  const isMissing = (section: SectionStatus) =>
    (section.status === "placeholder" || section.status === "outstanding") &&
    !documentsByLeaf.has(section.number);

  const visible = onlyMissing ? sections.filter(isMissing) : sections;
  const missingCount = sections.filter(isMissing).length;
  const modules = [...new Set(visible.map((s) => s.module))].sort();

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          What this dossier owes
        </h2>
        <Counts sections={sections} />
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={() => setOnlyMissing((previous) => !previous)}
            className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            {onlyMissing ? "Show every leaf" : `Show only what's missing (${missingCount})`}
          </button>
        </div>
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
            {visible
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
                  {section.copies.length > 0 && <Copies section={section} />}
                  {section.citation && section.status === "not-applicable" && (
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      Basis: {section.citation}
                    </p>
                  )}
                  {/* An uploadable leaf: the platform can place a file
                      here but can never author one. */}
                  {(section.status === "placeholder" ||
                    section.status === "outstanding" ||
                    documentsByLeaf.has(section.number)) && (
                    <DocumentControl
                      sectionNumber={section.number}
                      document={documentsByLeaf.get(section.number)}
                      busy={busy}
                      onUpload={(file) => upload(section, file)}
                      onRemove={() => remove(section)}
                    />
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
