"use client";

/**
 * Review one narrative slot: generate a draft, read it with its
 * citations, edit it, approve it.
 *
 * The gate this UI enforces is the one AGENTS.md §5 cares about --
 * "everything the LLM writes is reviewable". A PENDING draft is visibly
 * marked as not yet usable, because on the backend only approve/edit set
 * `final_text`, and only `final_text` reaches a rendered document. The
 * UI's job is to make that distinction impossible to miss, not to
 * re-implement it.
 */

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Narrative } from "@/lib/types";
import { Badge, Card, ErrorNotice } from "@/components/ui";

const buttonClass =
  "rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900";
const secondaryButtonClass =
  "rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-slate-700";

/** The newest generation is the one under review; earlier ones are history. */
function newest(generations: Narrative[]): Narrative | null {
  return generations.length ? generations[generations.length - 1] : null;
}

export function NarrativeSlot({
  projectId,
  section,
  slot,
  onChanged,
}: {
  projectId: string;
  section: string;
  slot: string;
  onChanged?: () => void;
}) {
  const [generations, setGenerations] = useState<Narrative[] | null>(null);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setGenerations(await api.listNarratives(projectId, section, slot));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load narratives");
    }
  }, [projectId, section, slot]);

  // The initial fetch is written out rather than calling `load()`, for two
  // reasons: the lint rule can't see that `load`'s setState happens after
  // an await (it flags the call as a synchronous cascading render), and
  // this version can cancel. Without the guard, switching tabs while a
  // request is in flight sets state on an unmounted component.
  useEffect(() => {
    let cancelled = false;
    api
      .listNarratives(projectId, section, slot)
      .then((rows) => {
        if (!cancelled) setGenerations(rows);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Could not load narratives",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, section, slot]);

  const current = generations ? newest(generations) : null;

  async function run(action: () => Promise<unknown>) {
    setError(null);
    setBusy(true);
    try {
      await action();
      await load();
      onChanged?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  // Compare against the backend's real (lowercase) values -- see the WHY
  // on NarrativeStatus in lib/types.ts. Display is uppercased separately.
  const isReviewed =
    current?.status === "approved" || current?.status === "edited";

  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{slot}</h4>
        {current ? (
          <Badge tone={isReviewed ? "good" : "bad"}>
            {isReviewed ? current.status.toUpperCase() : "awaiting review"}
          </Badge>
        ) : (
          <Badge>not drafted</Badge>
        )}
      </div>

      {error && <ErrorNotice message={error} />}

      {generations === null && (
        <p className="text-sm text-slate-500">Loading…</p>
      )}

      {generations !== null && current === null && (
        <div className="space-y-3">
          <p className="text-sm text-slate-600 dark:text-slate-400">
            No draft yet. Generation is grounded in the knowledge base and
            may only cite what it retrieved.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(() => api.generateNarrative(projectId, section, slot))
            }
            className={buttonClass}
          >
            {busy ? "Generating…" : "Generate draft"}
          </button>
        </div>
      )}

      {current && (
        <div className="space-y-3">
          {editing ? (
            <textarea
              rows={6}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          ) : (
            <p className="whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-sm dark:bg-slate-950">
              {current.final_text ?? current.output}
            </p>
          )}

          {current.warnings.length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
              <p className="mb-1 font-medium">Guardrail warnings</p>
              <ul className="list-inside list-disc space-y-0.5">
                {current.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="text-xs text-slate-500 dark:text-slate-400">
            <p className="font-medium">
              Sources ({current.sources.length}) · model {current.model_name}
            </p>
            {current.sources.length > 0 && (
              <ul className="mt-1 list-inside list-disc space-y-0.5">
                {current.sources.map((source) => (
                  <li key={source}>{source}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            {editing ? (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api.editNarrative(
                        projectId,
                        section,
                        slot,
                        current.id,
                        draft,
                      );
                      setEditing(false);
                    })
                  }
                  className={buttonClass}
                >
                  Save edit
                </button>
                <button
                  type="button"
                  onClick={() => setEditing(false)}
                  className={secondaryButtonClass}
                >
                  Cancel
                </button>
              </>
            ) : (
              <>
                {!isReviewed && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      run(() =>
                        api.approveNarrative(projectId, section, slot, current.id),
                      )
                    }
                    className={buttonClass}
                  >
                    {busy ? "Working…" : "Approve"}
                  </button>
                )}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setDraft(current.final_text ?? current.output);
                    setEditing(true);
                  }}
                  className={secondaryButtonClass}
                >
                  Edit
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    run(() => api.generateNarrative(projectId, section, slot))
                  }
                  className={secondaryButtonClass}
                >
                  Regenerate
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
