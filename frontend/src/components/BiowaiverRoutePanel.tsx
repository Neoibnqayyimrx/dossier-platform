"use client";

/**
 * The bioequivalence route, as one explicit choice (P22b).
 *
 * ## Why this is a panel and not two of the Sections tab's yes/no buttons
 *
 * Leaves 1.2.17 and 1.2.18 are both conditional, so the section list
 * already offers a three-state answer for each of them, and a filer could
 * in principle answer both there. That is the problem: presented as two
 * independent questions, "am I claiming a BCS biowaiver?" and "am I
 * claiming an additional-strength biowaiver?" look like two checkboxes,
 * and nothing on the screen says they are alternatives to each other AND
 * to filing an in vivo study.
 *
 * They are alternatives. A multisource filing takes exactly one route --
 * neither is an incomplete dossier, and both is a contradiction, because
 * the application would be saying at once that a human study was necessary
 * and that it was not. Rule R06 blocks the export either way; this panel
 * is what stops the filer getting there.
 *
 * ## Why the choice IS the condition answer
 *
 * There is no "route" field anywhere. The route is expressed as P17's
 * applicability answers, because that is what actually changes the
 * package: answering "yes" to 1.2.17 makes the leaf applicable, which is
 * what puts the request document in Module 1
 * (`SectionSpec.only_when_applicable`). A separate field would be a
 * preference recorded next to the thing it was supposed to control, and
 * the two could disagree.
 *
 * This is P17's machinery earning its keep: the biowaiver decision is not
 * wired to the section list, it IS the section list.
 */

import { useCallback, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { BIOWAIVER_ROUTE_LEAF, type BiowaiverRoute, type SectionStatus } from "@/lib/types";
import { Card, ErrorNotice } from "@/components/ui";

const ROUTES: Array<{
  route: BiowaiverRoute;
  title: string;
  blurb: string;
  leaves: string;
}> = [
  {
    route: "in-vivo",
    title: "In vivo bioequivalence study",
    blurb:
      "A human crossover or parallel study against the comparator. The default route, and the one most immediate-release generics take.",
    leaves: "Files 5.3.1.2 (study report), 5.3.1.4 (bioanalytical method), 1.4.1 (BTI form).",
  },
  {
    route: "bcs",
    title: "BCS-based biowaiver",
    blurb:
      "No human study: the argument is that a highly soluble, highly permeable drug in a rapidly dissolving product behaves like the comparator in vitro.",
    leaves: "Files 1.2.17. No study report is owed at 5.3.1.2.",
  },
  {
    route: "additional-strength",
    title: "Additional-strength biowaiver",
    blurb:
      "The study was run at another strength; this one is compositionally proportional with comparable dissolution.",
    leaves: "Files 1.2.18, and cites the in vivo study it leans on.",
  },
];

/** Which answers each route implies. Written out rather than derived,
 * because the negative half is load-bearing: choosing one route must
 * positively answer "no" to the other, not merely leave it unanswered.
 * An unanswered condition is silence, and R19 reports it as a WARNING
 * forever -- the filer HAS decided, and the dossier should say so. */
const ANSWERS: Record<BiowaiverRoute, Record<string, boolean>> = {
  "in-vivo": { "1.2.17": false, "1.2.18": false },
  bcs: { "1.2.17": true, "1.2.18": false },
  "additional-strength": { "1.2.17": false, "1.2.18": true },
};

/** Read the current route back out of the answers. `null` when nobody has
 * decided yet, and also when the answers are contradictory (both true) --
 * which the panel then shows as an explicit warning rather than silently
 * picking one. */
export function routeFrom(sections: SectionStatus[]): BiowaiverRoute | null | "contradictory" {
  const answer = (number: string) =>
    sections.find((section) => section.number === number)?.answer ?? null;
  const bcs = answer("1.2.17");
  const additional = answer("1.2.18");
  if (bcs === true && additional === true) return "contradictory";
  if (bcs === true) return "bcs";
  if (additional === true) return "additional-strength";
  if (bcs === false && additional === false) return "in-vivo";
  return null;
}

export function BiowaiverRoutePanel({
  projectId,
  sections,
  onChanged,
}: {
  projectId: string;
  sections: SectionStatus[];
  onChanged: (sections: SectionStatus[]) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const current = routeFrom(sections);

  const choose = useCallback(
    async (route: BiowaiverRoute) => {
      setBusy(true);
      setError(null);
      try {
        // Both answers in ONE request. Sent separately, a failure between
        // them would leave the project claiming two routes at once -- the
        // state this panel exists to make unreachable.
        onChanged(await api.answerConditions(projectId, ANSWERS[route]));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not record that choice");
      } finally {
        setBusy(false);
      }
    },
    [projectId, onChanged],
  );

  return (
    <Card>
      <h3 className="text-sm font-semibold">Bioequivalence route</h3>
      <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
        A multisource filing takes exactly one of these. Choosing changes which
        leaves your dossier owes — rule R06 blocks the export if two routes are
        filed, or none.
      </p>

      {error && (
        <div className="mt-2">
          <ErrorNotice message={error} />
        </div>
      )}

      {current === "contradictory" && (
        <p className="mt-2 rounded-md border border-red-300 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:text-red-400">
          Both biowaiver leaves are currently answered “yes”. Pick one route below.
        </p>
      )}
      {current === null && (
        <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
          Not yet decided — 1.2.17 and 1.2.18 are unanswered, which rule R19
          reports as a warning.
        </p>
      )}

      <div className="mt-3 space-y-2">
        {ROUTES.map((option) => {
          const selected = current === option.route;
          return (
            <button
              key={option.route}
              type="button"
              disabled={busy}
              onClick={() => void choose(option.route)}
              className={`block w-full rounded-md border px-3 py-2 text-left text-sm disabled:opacity-50 ${
                selected
                  ? "border-slate-900 bg-slate-50 dark:border-slate-200 dark:bg-slate-800"
                  : "border-slate-200 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
              }`}
            >
              <span className="font-medium">{option.title}</span>
              {selected && <span className="ml-2 text-xs text-slate-500">— chosen</span>}
              <span className="mt-1 block text-xs text-slate-600 dark:text-slate-400">
                {option.blurb}
              </span>
              <span className="mt-1 block text-xs text-slate-500">{option.leaves}</span>
            </button>
          );
        })}
      </div>

      {current !== null && current !== "contradictory" && BIOWAIVER_ROUTE_LEAF[current] && (
        <p className="mt-3 text-xs text-slate-600 dark:text-slate-400">
          Enter the request’s supporting data (BCS class, f2 similarity, the
          strength it covers) on the product’s bioequivalence step —{" "}
          {BIOWAIVER_ROUTE_LEAF[current]} ships with nothing in it otherwise, and
          rule R06 says so.
        </p>
      )}
    </Card>
  );
}
