"use client";

/**
 * Download the validation report as a PDF (gap Phase 5b).
 *
 * WHY a button beside the findings rather than a print stylesheet: the
 * report is built on the server from the same findings the API returns,
 * so the document someone forwards says exactly what the platform decided
 * -- including which checks were waived and why, which the list on screen
 * shows only as a badge.
 */

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { ErrorNotice } from "@/components/ui";

const buttonClass =
  "rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-slate-700";

export function ReportDownloadButton({ projectId }: { projectId: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setError(null);
    setBusy(true);
    try {
      await api.downloadValidationReport(projectId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not produce the report");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" disabled={busy} onClick={download} className={buttonClass}>
        {busy ? "Preparing report…" : "Download report (PDF)"}
      </button>
      {error && <ErrorNotice message={error} />}
    </div>
  );
}
