"use client";

import { use, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Finding, Project, ReadinessResponse } from "@/lib/types";
import { AuthGuard } from "@/components/AuthGuard";
import {
  Badge,
  Card,
  ErrorNotice,
  PageHeading,
  SeverityBadge,
} from "@/components/ui";

function Facts({ project }: { project: Project }) {
  const p = project.product;
  const rows: [string, string][] = [
    ["Brand name", p.brand_name],
    ["Generic name", p.generic_name],
    ["Strength", p.strength_display || "—"],
    ["Dosage form", p.dosage_form ?? "—"],
    ["Shelf life", p.shelf_life_months ? `${p.shelf_life_months} months` : "—"],
    ["Storage", p.storage_condition ?? "—"],
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

/**
 * Findings are grouped by category rather than listed flat, matching how
 * `Report.by_category()` already thinks about them on the backend -- a
 * reviewer fixes a dossier one concern at a time, not one row at a time.
 */
function Readiness({ readiness }: { readiness: ReadinessResponse }) {
  const grouped = readiness.findings.reduce<Record<string, Finding[]>>(
    (acc, finding) => {
      (acc[finding.category] ??= []).push(finding);
      return acc;
    },
    {},
  );

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Readiness
        </h2>
        <Badge tone={readiness.is_exportable ? "good" : "bad"}>
          {readiness.is_exportable ? "Exportable" : "Blocked"}
        </Badge>
      </div>

      {readiness.findings.length === 0 ? (
        <p className="text-sm text-slate-600 dark:text-slate-400">
          No findings.
        </p>
      ) : (
        <div className="space-y-4">
          {Object.entries(grouped).map(([category, findings]) => (
            <div key={category}>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                {category}
              </h3>
              <ul className="space-y-2">
                {findings.map((finding, index) => (
                  <li
                    key={`${finding.rule_id}-${index}`}
                    className="flex items-start gap-3 text-sm"
                  >
                    <SeverityBadge severity={finding.severity} />
                    <span className="flex-1">
                      {finding.message}
                      <span className="ml-2 font-mono text-xs text-slate-400">
                        {finding.rule_id}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {readiness.overridden_rule_ids.length > 0 && (
        <p className="mt-4 border-t border-slate-200 pt-3 text-xs text-slate-500 dark:border-slate-800">
          Overridden by a human with a logged reason:{" "}
          <span className="font-mono">
            {readiness.overridden_rule_ids.join(", ")}
          </span>
        </p>
      )}
    </Card>
  );
}

function ProjectDetail({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getProject(projectId), api.getReadiness(projectId)])
      .then(([projectResult, readinessResult]) => {
        setProject(projectResult);
        setReadiness(readinessResult);
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
        actions={<Badge>{project.region}</Badge>}
      />
      <div className="space-y-4">
        <Facts project={project} />
        <Readiness readiness={readiness} />
      </div>
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
