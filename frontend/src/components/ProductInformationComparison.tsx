"use client";

/**
 * The SmPC, the label and the leaflet side by side (P23).
 *
 * ## What this screen is actually showing
 *
 * A pharmacist reads three columns and recognises the check immediately:
 * this is the cross-read an assessor does with three printed documents on
 * a desk, and it is where the most commonly raised deficiency in Module 1
 * is found -- a shelf-life extension that updated two of the three, a
 * storage statement rewritten for a new market on one document only.
 *
 * The screen's answer is "0 divergences", and the interesting part is WHY.
 * Not because the three were checked and happened to match: because all
 * three render from one dataset, so there is one expression of each value
 * and nothing to disagree with. The provenance line under each row is what
 * makes that visible rather than merely asserted -- it names the one place
 * the value comes from.
 *
 * ## Why the count comes from the server
 *
 * `agrees` and `divergences` are computed by the backend, not here. They
 * are a regulatory verdict, and rule R31 makes the same call on the same
 * data at export time. Two implementations of "do these agree" is exactly
 * the second copy this phase exists to remove -- it would be absurd to
 * introduce one in the screen that demonstrates removing it.
 */

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { ComparisonRow, ThreeWayComparison } from "@/lib/types";
import { Badge, Card, ErrorNotice } from "@/components/ui";

/** Short column headers. The section numbers stay because they are how an
 * assessor refers to the documents; the titles are too long for a column. */
const COLUMN_LABEL: Record<string, string> = {
  "1.3.1": "SmPC",
  "1.3.2": "Label",
  "1.3.3": "Leaflet",
};

function Row({ row }: { row: ComparisonRow }) {
  return (
    <div
      className={`rounded-md border p-3 ${
        row.agrees
          ? "border-slate-200 dark:border-slate-800"
          : "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/40"
      }`}
    >
      <div className="flex flex-wrap items-baseline gap-2">
        {row.smpc_section && (
          <span className="font-mono text-xs text-slate-400">{row.smpc_section}</span>
        )}
        <span className="text-sm font-medium">{row.label}</span>
        {row.agrees ? (
          <Badge tone="good">agrees</Badge>
        ) : (
          <Badge tone="bad">divergent</Badge>
        )}
      </div>

      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        {row.values.map((value) => (
          <div key={value.section}>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              <span className="font-mono">{value.section}</span>{" "}
              {COLUMN_LABEL[value.section] ?? value.document}
            </div>
            <div className="text-sm">{value.value || "—"}</div>
          </div>
        ))}
      </div>

      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{row.source}</p>
    </div>
  );
}

export function ProductInformationComparison({ projectId }: { projectId: string }) {
  const [comparison, setComparison] = useState<ThreeWayComparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The house pattern for a fetch-on-mount (SpecificationEditor,
  // BioequivalenceEditor): the promise chain is inline and `cancelled`
  // guards the setState, so a response that arrives after the project id
  // changed cannot overwrite the newer one. It also keeps the lint rule
  // happy for the right reason -- nothing sets state synchronously in the
  // effect body.
  useEffect(() => {
    let cancelled = false;
    api
      .compareProductInformation(projectId)
      .then((loaded) => {
        if (!cancelled) setComparison(loaded);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load the comparison");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (error) return <ErrorNotice message={error} />;
  if (!comparison) return null;

  const { rows, divergences } = comparison;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Product information cross-check</h2>
          <p className="mt-1 max-w-2xl text-xs text-slate-500 dark:text-slate-400">
            What the SmPC (1.3.1), the labels (1.3.2) and the patient leaflet (1.3.3)
            each print for every fact they share. All three are rendered from one
            dataset, so a divergence would mean a second copy of a value has been
            introduced somewhere — rule R31 blocks the export if it ever happens.
          </p>
        </div>
        {divergences === 0 ? (
          <Badge tone="good">no divergences</Badge>
        ) : (
          <Badge tone="bad">
            {divergences} divergence{divergences === 1 ? "" : "s"}
          </Badge>
        )}
      </div>

      <div className="mt-4 space-y-2">
        {rows.map((row) => (
          <Row key={row.field} row={row} />
        ))}
      </div>
    </Card>
  );
}
