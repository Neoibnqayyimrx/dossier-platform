"use client";

/**
 * Module 1: who is filing, and the administrative documents the region
 * demands.
 *
 * WHY this lives on the project page and not in the wizard: a Declaration
 * belongs to the PROJECT (a Power of Attorney names a representative for
 * this specific filing -- next year's renewal may appoint someone else),
 * and the wizard does not create the project until its final step. There
 * would be nothing to attach a declaration to.
 *
 * WHY the required list comes from the server: which documents a filing
 * must carry is a regional fact, and it is the same list rules R13/R16
 * validate against (see app/api/routers/regions.py). A hard-coded copy
 * here is how the form and the rule engine start disagreeing about what
 * a dossier needs.
 */

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type {
  Applicant,
  Declaration,
  Project,
  RegionProfile,
  Vocabularies,
} from "@/lib/types";
import { Badge, Card, ErrorNotice } from "@/components/ui";

const buttonClass =
  "rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-slate-700";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function DeclarationRow({
  projectId,
  declarationType,
  label,
  declaration,
  required,
  onChanged,
}: {
  projectId: string;
  declarationType: string;
  label: string;
  declaration: Declaration | undefined;
  required: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    setBusy(true);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{label}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {required && <Badge>required here</Badge>}
            {declaration === undefined ? (
              <Badge tone="bad">not on file</Badge>
            ) : (
              <>
                <Badge tone={declaration.signed ? "good" : "bad"}>
                  {declaration.signed ? "signed" : "unsigned"}
                </Badge>
                <Badge tone={declaration.notarized ? "good" : "neutral"}>
                  {declaration.notarized ? "notarised" : "not notarised"}
                </Badge>
              </>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {declaration === undefined ? (
            <button
              type="button"
              disabled={busy}
              className={buttonClass}
              onClick={() =>
                run(() =>
                  api.createDeclaration(projectId, { declaration_type: declarationType }),
                )
              }
            >
              Add
            </button>
          ) : (
            <>
              {/* The signed/notarised flags record something the platform
                  cannot observe -- a human put a pen on paper. Marking one
                  is an assertion by the person clicking, which is exactly
                  why rule R15 trusts it to unblock an export. */}
              <button
                type="button"
                disabled={busy}
                className={buttonClass}
                onClick={() =>
                  run(() =>
                    api.updateDeclaration(projectId, declaration.id, {
                      signed: !declaration.signed,
                      signed_date: declaration.signed ? null : todayIso(),
                    }),
                  )
                }
              >
                {declaration.signed ? "Mark unsigned" : "Mark signed"}
              </button>
              <button
                type="button"
                disabled={busy}
                className={buttonClass}
                onClick={() =>
                  run(() =>
                    api.updateDeclaration(projectId, declaration.id, {
                      notarized: !declaration.notarized,
                      notarization_date: declaration.notarized ? null : todayIso(),
                    }),
                  )
                }
              >
                {declaration.notarized ? "Mark un-notarised" : "Mark notarised"}
              </button>
              <button
                type="button"
                disabled={busy}
                className="text-xs text-slate-500 hover:text-red-600"
                onClick={() => run(() => api.deleteDeclaration(projectId, declaration.id))}
              >
                Remove
              </button>
            </>
          )}
        </div>
      </div>
      {error && (
        <div className="mt-2">
          <ErrorNotice message={error} />
        </div>
      )}
    </li>
  );
}

function ApplicantCard({
  project,
  applicants,
  onChanged,
}: {
  project: Project;
  applicants: Applicant[];
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function choose(applicantId: string) {
    if (!applicantId) return;
    setError(null);
    setBusy(true);
    try {
      await api.updateProject(project.id, { applicant_id: applicantId });
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Applicant
      </h3>
      {project.applicant ? (
        <div className="text-sm">
          <p className="font-medium">{project.applicant.company_name}</p>
          <p className="text-slate-500 dark:text-slate-400">
            {[project.applicant.address, project.applicant.country]
              .filter(Boolean)
              .join(", ") || "—"}
          </p>
          {project.applicant.authorized_representative_name && (
            <p className="mt-1 text-slate-500 dark:text-slate-400">
              Signatory: {project.applicant.authorized_representative_name}
              {project.applicant.authorized_representative_title
                ? ` (${project.applicant.authorized_representative_title})`
                : ""}
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm text-slate-600 dark:text-slate-400">
          No applicant named yet — rule R14 blocks export until one is.
        </p>
      )}

      {applicants.length > 0 && (
        <div className="mt-3">
          <label htmlFor="project-applicant" className="mb-1 block text-sm font-medium">
            {project.applicant ? "Change applicant" : "Name the applicant"}
          </label>
          <select
            id="project-applicant"
            disabled={busy}
            value={project.applicant?.id ?? ""}
            onChange={(e) => choose(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="">— select —</option>
            {applicants.map((applicant) => (
              <option key={applicant.id} value={applicant.id}>
                {applicant.company_name}
              </option>
            ))}
          </select>
        </div>
      )}
      {error && (
        <div className="mt-2">
          <ErrorNotice message={error} />
        </div>
      )}
    </Card>
  );
}

export function Module1Panel({
  project,
  vocabularies,
  onChanged,
}: {
  project: Project;
  vocabularies: Vocabularies;
  onChanged: () => void;
}) {
  const [profile, setProfile] = useState<RegionProfile | null>(null);
  const [applicants, setApplicants] = useState<Applicant[]>([]);
  const [error, setError] = useState<string | null>(null);

  /**
   * WHY there is no local copy of the declarations: GET /projects/{id}
   * already returns them, so a second source of truth here could only
   * drift from the project the rest of the page is rendering (and
   * syncing one to the other in an effect is the anti-pattern
   * react-hooks/set-state-in-effect exists to catch). Every mutation
   * asks the parent to refetch instead -- which it must do anyway, since
   * signing a declaration changes the readiness report too.
   */
  const declarations = project.declarations;

  useEffect(() => {
    api
      .listRegionProfiles()
      .then((profiles) => setProfile(profiles.find((p) => p.region === project.region) ?? null))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not reach the server"),
      );
    api.listApplicants().then(setApplicants).catch(() => {});
  }, [project.region]);

  const labels = new Map(
    (vocabularies["declaration_type"] ?? []).map((option) => [option.value, option.label]),
  );
  const required = profile?.required_declaration_types ?? [];
  // Everything required, plus anything already attached that isn't --
  // a GMP undertaking is optional for NAFDAC but must still be visible
  // and signable once someone has added it.
  const shown = [...required, ...declarations.map((d) => d.declaration_type).filter((t) => !required.includes(t))];

  return (
    <div className="space-y-4">
      {error && <ErrorNotice message={error} />}

      <ApplicantCard project={project} applicants={applicants} onChanged={onChanged} />

      <Card>
        <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Declarations
        </h3>
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">
          The platform writes these documents from your data, but they are
          only real once a human signs them — and, for some, a notary seals
          them. Marking one signed here is that human saying so.
        </p>

        {profile !== null && required.length === 0 && (
          <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">
            This region&apos;s Module 1 requirements are not modelled yet — that
            is not the same as nothing being required. Confirm them against
            the agency&apos;s current guidance before filing.
          </p>
        )}

        <ul className="space-y-2">
          {shown.map((declarationType) => (
            <DeclarationRow
              key={declarationType}
              projectId={project.id}
              declarationType={declarationType}
              label={labels.get(declarationType) ?? declarationType}
              declaration={declarations.find((d) => d.declaration_type === declarationType)}
              required={required.includes(declarationType)}
              onChanged={onChanged}
            />
          ))}
        </ul>
      </Card>
    </div>
  );
}
