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
 */

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { EctdBuildResponse, Region } from "@/lib/types";
import { Badge, Card, ErrorNotice } from "@/components/ui";

const buttonClass =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900";
const secondaryButtonClass =
  "rounded-md border border-slate-300 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-slate-700";

export function BuildPanel({
  projectId,
  region,
}: {
  projectId: string;
  region: Region;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [ctdKey, setCtdKey] = useState<string | null>(null);
  const [ectd, setEctd] = useState<EctdBuildResponse | null>(null);

  // NAFDAC files a CTD; FDA/EU file an eCTD sequence. See the module WHY.
  const buildsEctd = region !== "NAFDAC";

  async function run(label: string, action: () => Promise<void>) {
    setError(null);
    setBusy(label);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Build failed");
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
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={busy !== null}
              onClick={() =>
                run("ectd", async () => {
                  // A sequence is a regulatory transaction, numbered by
                  // the backend (0000, 0001, ...) -- the UI never invents
                  // that number.
                  const sequence = await api.createSequence(projectId);
                  setEctd(await api.buildEctd(projectId, sequence.id));
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
