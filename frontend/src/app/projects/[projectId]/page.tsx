"use client";

import { use, useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type {
  Project,
  ReadinessResponse,
  SectionSpec,
  ValidationOverride,
  Vocabularies,
} from "@/lib/types";
import { AuthGuard } from "@/components/AuthGuard";
import { BuildPanel } from "@/components/BuildPanel";
import { Module1Panel } from "@/components/Module1Panel";
import { ReportDownloadButton } from "@/components/ReportDownloadButton";
import { OverridePanel } from "@/components/OverridePanel";
import { ProductInformationComparison } from "@/components/ProductInformationComparison";
import { SectionListPanel } from "@/components/SectionListPanel";
import { NarrativeSlot } from "@/components/NarrativeSlot";
import { ValidationReport } from "@/components/ValidationReport";
import { Badge, Card, ErrorNotice, PageHeading } from "@/components/ui";

// Module 1 sits between the data and the narrative work deliberately: it
// is the administrative half of a filing (who is applying, what they have
// signed), and on a NAFDAC dossier it is the most common reason an
// otherwise complete package cannot be exported.
// "Sections" sits directly after Module 1 and before the narrative work: it
// answers "what does this dossier still owe?", which is the question you ask
// BEFORE deciding what to write (P17). It is also where the conditional
// questions are answered, and those change what the other tabs show.
// P23: "Product information" sits directly after Module 1, because that is
// where it is filed (1.3) and because the question it answers -- do the
// SmPC, the label and the leaflet agree? -- is one an assessor asks of the
// administrative half of the dossier, not of the narrative work.
const TABS = [
  "Overview",
  "Module 1",
  "Product information",
  "Sections",
  "Narratives",
  "Validation",
  "Build",
] as const;
type Tab = (typeof TABS)[number];

function Facts({ project }: { project: Project }) {
  const p = project.product;
  const rows: [string, string][] = [
    ["Brand name", p.brand_name],
    ["Generic name", p.generic_name],
    ["Strength", p.strength_display || "—"],
    ["Dosage form", p.dosage_form ?? "—"],
    ["Shelf life", p.shelf_life_months ? `${p.shelf_life_months} months` : "—"],
    ["Storage", p.storage_condition ?? "—"],
    ["Applicant", project.applicant?.company_name ?? "— not named yet"],
    ["Manufacturers", String(p.manufacturers.length)],
    ["Active ingredients", String(p.apis.length)],
    ["Excipients", String(p.excipients.length)],
    ["Stability studies", String(p.stability.length)],
  ];
  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Product
      </h2>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 text-sm">
            <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
            <dd className="text-right font-medium">{value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function Narratives({
  projectId,
  sections,
  onChanged,
}: {
  projectId: string;
  sections: SectionSpec[];
  onChanged: () => void;
}) {
  // Sections with no slots (e.g. 1.2.2, the registration form) are shown but
  // not offered a drafting UI -- every fact on them is structured data
  // already, so there is nothing for a model to write.
  return (
    <div className="space-y-6">
      {sections.map((section) => (
        <div key={section.number}>
          <div className="mb-2 flex items-center gap-2">
            <h3 className="font-medium">
              {section.number} — {section.title}
            </h3>
            {section.narrative_slots.length === 0 && (
              <Badge>data only</Badge>
            )}
          </div>
          {section.narrative_slots.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Generated entirely from structured data — no narrative to review.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {section.narrative_slots.map((slot) => (
                <NarrativeSlot
                  key={slot}
                  projectId={projectId}
                  section={section.number}
                  slot={slot}
                  onChanged={onChanged}
                />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ProjectDetail({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [sections, setSections] = useState<SectionSpec[]>([]);
  const [vocabularies, setVocabularies] = useState<Vocabularies | null>(null);
  const [overrides, setOverrides] = useState<ValidationOverride[]>([]);
  const [tab, setTab] = useState<Tab>("Overview");
  const [error, setError] = useState<string | null>(null);

  const refreshReadiness = useCallback(() => {
    api.getReadiness(projectId).then(setReadiness).catch(() => {});
    // Overrides and readiness move together: recording or withdrawing one
    // changes the export gate, so refreshing either alone would leave the
    // page showing a verdict that no longer matches its own reasons.
    api.listOverrides(projectId).then(setOverrides).catch(() => {});
  }, [projectId]);

  // Module 1 edits change both the project (its applicant, its
  // declarations) and what the rules say about it, so the panel's
  // onChanged has to refresh both -- otherwise you sign a declaration and
  // the export gate keeps reporting the finding you just cleared.
  const refreshProject = useCallback(() => {
    api.getProject(projectId).then(setProject).catch(() => {});
    refreshReadiness();
  }, [projectId, refreshReadiness]);

  useEffect(() => {
    Promise.all([
      api.getProject(projectId),
      api.getReadiness(projectId),
      api.getSections(),
      api.getEnums(),
      api.listOverrides(projectId),
    ])
      .then(([projectResult, readinessResult, sectionsResult, vocabularyResult, overrideResult]) => {
        setProject(projectResult);
        setReadiness(readinessResult);
        setSections(sectionsResult);
        setVocabularies(vocabularyResult);
        setOverrides(overrideResult);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Could not reach the server",
        ),
      );
  }, [projectId]);

  if (error) return <ErrorNotice message={error} />;
  if (!project || !readiness)
    return <p className="text-sm text-slate-500">Loading project…</p>;

  return (
    <>
      <PageHeading
        title={project.name}
        subtitle={`${project.region} · ${project.product.brand_name}`}
        actions={
          <div className="flex items-center gap-2">
            {/* The submission type is shown next to the export verdict
                because it is the thing that decides what "complete" even
                means for this dossier (P17). */}
            <Badge>{project.submission_type}</Badge>
            <Badge tone={readiness.is_exportable ? "good" : "bad"}>
              {readiness.is_exportable ? "Exportable" : "Blocked"}
            </Badge>
          </div>
        }
      />

      <div className="mb-5 flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              tab === name
                ? "border-slate-900 font-medium dark:border-slate-100"
                : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
            }`}
          >
            {name}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="space-y-4">
          <Facts project={project} />
          <ValidationReport
            findings={readiness.findings}
            isExportable={readiness.is_exportable}
            overriddenRuleIds={readiness.overridden_rule_ids}
            title="Readiness"
          />
        </div>
      )}

      {tab === "Module 1" && vocabularies !== null && (
        <Module1Panel
          project={project}
          vocabularies={vocabularies}
          onChanged={refreshProject}
        />
      )}

      {tab === "Product information" && (
        <ProductInformationComparison projectId={projectId} />
      )}

      {tab === "Sections" && (
        <SectionListPanel projectId={projectId} onChanged={refreshReadiness} />
      )}

      {tab === "Narratives" && (
        <Narratives
          projectId={projectId}
          sections={sections}
          onChanged={refreshReadiness}
        />
      )}

      {tab === "Validation" && (
        <div className="space-y-4">
          <ReportDownloadButton projectId={projectId} />
          <ValidationReport
            findings={readiness.findings}
            isExportable={readiness.is_exportable}
            overriddenRuleIds={readiness.overridden_rule_ids}
            title="Deterministic data rules"
            emptyMessage="No findings — every data rule passed."
          />
          <OverridePanel
            projectId={projectId}
            findings={readiness.findings}
            overrides={overrides}
            onChanged={refreshReadiness}
          />
        </div>
      )}

      {tab === "Build" && (
        <BuildPanel
          projectId={projectId}
          region={project.region}
          sequenceCount={project.sequences.length}
          vocabularies={vocabularies}
        />
      )}
    </>
  );
}

export default function ProjectPage({
  params,
}: PageProps<"/projects/[projectId]">) {
  // Next 16 passes route params as a Promise; `use()` unwraps it inside
  // this Client Component.
  const { projectId } = use(params);
  return (
    <AuthGuard>
      <ProjectDetail projectId={projectId} />
    </AuthGuard>
  );
}
