"use client";

/**
 * Build and download the dossier.
 *
 * WHY the eCTD builder is offered per region rather than always: a NAFDAC
 * filing genuinely has no XML backbone (reference/nafdac-vs-fda-ema-scope.md)
 * — the CTD folder + TOC package *is* the deliverable there. Offering an
 * eCTD build for NAFDAC would invite a user to produce something no one
 * asked for; offering a CTD build for EU would produce something no
 * gateway accepts. The region drives which builder is real, matching the
 * backend's own region profiles rather than a second opinion here.
 *
 * WHY builds are not gated in this component: P07's assemble step already
 * refuses to produce anything when validation has unresolved errors, and
 * the API answers 409. Re-implementing that check here would be a second
 * source of truth for "is this exportable" — instead the button stays
 * live and the 409's message is shown, which is also the honest behaviour
 * when a human has logged an override.
 *
 * WHY the filer chooses what kind of transaction a new sequence is (gap
 * Phase 4c): the button used to create every sequence as `initial`, because
 * the type could only be set by a separate PATCH nobody made. The EU envelope
 * then filed answers to the agency as fresh submissions, and FDA -- which
 * allows one "application" per regulatory activity -- refused every build
 * after the first. The type is the filer's statement, so it is asked for
 * here, defaulted to what it almost always is.
 */

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { BlockingFinding } from "@/lib/api";
import { defaultSubmissionUnitType } from "@/lib/sequence-type";
import type {
  EctdBuildResponse,
  OverrideSummary,
  Region,
  Sequence,
  Vocabularies,
} from "@/lib/types";
import { Badge, Card, ErrorNotice } from "@/components/ui";

const buttonClass =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900";
const secondaryButtonClass =
  "rounded-md border border-slate-300 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-slate-700";

export function BuildPanel({
  projectId,
  region,
  sequenceCount,
  vocabularies,
}: {
  projectId: string;
  region: Region;
  /** How many sequences the project already has -- decides the default. */
  sequenceCount: number;
  vocabularies: Vocabularies | null;
}) {
  const [error, setError] = useState<string | null>(null);
  // P18: which leaves refused the build. Kept apart from `error` because a
  // refusal is not a malfunction -- it is the ordinary state of a filing
  // whose paper is not all in, and it deserves a list to work through
  // rather than a red paragraph.
  const [blocking, setBlocking] = useState<BlockingFinding[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [ctdKey, setCtdKey] = useState<string | null>(null);
  const [ectd, setEctd] = useState<EctdBuildResponse | null>(null);
  // What the build was allowed to ignore. A package assembled over a
  // waived ERROR is byte-for-byte as convincing as one that passed
  // cleanly, so the only place that distinction can surface is here.
  const [waived, setWaived] = useState<OverrideSummary[]>([]);
  // Counted here rather than refetched: each successful eCTD build adds
  // exactly one sequence, and the next default follows from that.
  const [sequences, setSequences] = useState(sequenceCount);
  const [unitType, setUnitType] = useState(() => defaultSubmissionUnitType(sequenceCount));
  const unitTypes = vocabularies?.["submission_unit_type"] ?? [];
  // A sequence this panel created whose build was then refused. The next
  // attempt builds THAT sequence rather than creating another: sequence
  // numbers are regulatory identifiers, and a refused build must not burn
  // one. For FDA it is worse than untidy -- the unbuilt sequence would sit
  // on file as the "original application", and the real one could only be
  // filed as an amendment to something FDA never received.
  const [pending, setPending] = useState<Sequence | null>(null);

  // NAFDAC files a CTD; FDA/EU file an eCTD sequence. See the module WHY.
  const buildsEctd = region !== "NAFDAC";

  async function run(label: string, action: () => Promise<void>) {
    setError(null);
    setBlocking([]);
    setBusy(label);
    try {
      await action();
    } catch (err) {
      if (err instanceof ApiError && err.blocking.length > 0) {
        setBlocking(err.blocking);
      } else {
        setError(err instanceof ApiError ? err.message : "Build failed");
      }
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Build
        </h2>
        <Badge>{buildsEctd ? "eCTD sequence" : "CTD package"}</Badge>
      </div>

      {error && <ErrorNotice message={error} />}

      {blocking.length > 0 && (
        <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-900 dark:bg-amber-950/40">
          <p className="font-medium">
            {blocking.length === 1
              ? "One leaf is holding this build up:"
              : `${blocking.length} leaves are holding this build up:`}
          </p>
          <ul className="mt-2 space-y-1">
            {blocking.map((finding, index) => (
              <li key={`${finding.rule_id}-${index}`} className="flex gap-2">
                <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
                  {finding.section ?? finding.rule_id}
                </span>
                <span>{finding.message}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
            Attach the missing documents on the Sections tab. If a document
            genuinely cannot be supplied for this submission, record an
            override with a reason on the Validation tab — that is the
            deliberate exception, and it is reported on every build.
          </p>
        </div>
      )}

      {waived.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-900 dark:bg-amber-950/40">
          <p className="font-medium">
            This package was built over {waived.length} waived{" "}
            {waived.length === 1 ? "check" : "checks"}.
          </p>
          <ul className="mt-1 space-y-0.5 text-xs text-slate-700 dark:text-slate-300">
            {waived.map((override) => (
              <li key={override.rule_id}>
                <span className="font-mono">{override.rule_id}</span> — {override.reason}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
            The record stays on the Validation tab. It is not written into
            the package — a deviation record is your quality documentation,
            not submission content.
          </p>
        </div>
      )}

      <p className="text-sm text-slate-600 dark:text-slate-400">
        {buildsEctd
          ? "This region expects an eCTD: a sequenced package with an XML backbone, per-leaf checksums and lifecycle operations."
          : "NAFDAC expects a CTD: structured folders, PDFs and a table of contents. No XML backbone is required."}
      </p>

      {!buildsEctd && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() =>
              run("ctd", async () => {
                const result = await api.buildCtd(projectId);
                setCtdKey(result.storage_key);
                setWaived(result.overrides);
              })
            }
            className={buttonClass}
          >
            {busy === "ctd" ? "Building…" : "Build CTD package"}
          </button>
          {ctdKey && (
            <button
              type="button"
              onClick={() =>
                run("download-ctd", () =>
                  api.downloadArtifact(projectId, ctdKey),
                )
              }
              className={secondaryButtonClass}
            >
              Download .zip
            </button>
          )}
        </div>
      )}

      {buildsEctd && (
        <div className="space-y-3">
          {unitTypes.length > 0 && (
            <div className="max-w-xs">
              <label htmlFor="sequence-unit-type" className="mb-1 block text-sm font-medium">
                The next sequence is
              </label>
              <select
                id="sequence-unit-type"
                value={unitType}
                disabled={busy !== null}
                onChange={(e) => setUnitType(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              >
                {unitTypes.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                {region === "FDA"
                  ? 'FDA takes one "initial" (the original application). Every later sequence is an amendment, so choose "response".'
                  : "What this transaction is: the first filing, or an answer to the agency."}
              </p>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={busy !== null}
              onClick={() =>
                run("ectd", async () => {
                  // A sequence is a regulatory transaction, numbered by
                  // the backend (0000, 0001, ...) -- the UI never invents
                  // that number.
                  let sequence = pending;
                  if (sequence === null) {
                    sequence = await api.createSequence(projectId, {
                      submission_unit_type: unitType,
                    });
                    setPending(sequence);
                  } else if (sequence.submission_unit_type !== unitType) {
                    sequence = await api.updateSequence(projectId, sequence.id, {
                      submission_unit_type: unitType,
                    });
                    setPending(sequence);
                  }
                  const result = await api.buildEctd(projectId, sequence.id);
                  setPending(null);
                  setEctd(result);
                  setWaived(result.overrides);
                  setSequences(sequences + 1);
                  setUnitType(defaultSubmissionUnitType(sequences + 1));
                })
              }
              className={buttonClass}
            >
              {busy === "ectd" ? "Building…" : "Build next eCTD sequence"}
            </button>
            {ectd && (
              <button
                type="button"
                onClick={() =>
                  run("download-ectd", () =>
                    api.downloadArtifact(projectId, ectd.storage_key),
                  )
                }
                className={secondaryButtonClass}
              >
                Download sequence {ectd.sequence_number}
              </button>
            )}
          </div>

          {ectd && (
            <div className="text-xs text-slate-600 dark:text-slate-400">
              <p className="mb-1 font-medium">
                Sequence {ectd.sequence_number} — lifecycle operations
              </p>
              {Object.keys(ectd.operations).length === 0 ? (
                <p>
                  Nothing changed since the previous sequence, so this one
                  restates nothing — that is what an eCTD is supposed to do.
                </p>
              ) : (
                <ul className="list-inside list-disc space-y-0.5">
                  {Object.entries(ectd.operations).map(([key, operation]) => (
                    <li key={key}>
                      <span className="font-mono">{key}</span> — {operation}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
