"use client";

/**
 * The consolidated validation viewer.
 *
 * Findings arrive from up to four independent layers (P06 data rules, the
 * mechanical eCTD checks, an external validator, and the AI reviewer) and
 * every one carries a `source`. Showing that provenance is the whole
 * point: "this number is inconsistent" (deterministic, blocking) and
 * "you might want to mention the intermediate condition" (advisory, from
 * a language model) are different kinds of claim, and a reviewer must
 * never have to guess which one they're reading.
 */

import type { Finding, Severity } from "@/lib/types";
import { Badge, Card, SeverityBadge } from "@/components/ui";

const SOURCE_LABELS: Record<string, string> = {
  "data-rule": "data rule",
  "mechanical-ectd": "eCTD check",
  "external-validator": "external validator",
  "ai-reviewer": "AI reviewer",
};

const SEVERITY_ORDER: Severity[] = ["ERROR", "WARNING", "INFO", "ADVISORY"];

export function ValidationReport({
  findings,
  isExportable,
  overriddenRuleIds = [],
  title = "Validation",
  emptyMessage = "No findings.",
}: {
  findings: Finding[];
  isExportable: boolean;
  overriddenRuleIds?: string[];
  title?: string;
  emptyMessage?: string;
}) {
  const grouped = findings.reduce<Record<string, Finding[]>>((acc, finding) => {
    (acc[finding.category] ??= []).push(finding);
    return acc;
  }, {});

  const counts = SEVERITY_ORDER.map((severity) => ({
    severity,
    count: findings.filter((f) => f.severity === severity).length,
  })).filter((entry) => entry.count > 0);

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          {title}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          {counts.map(({ severity, count }) => (
            <span key={severity} className="flex items-center gap-1 text-xs">
              <SeverityBadge severity={severity} />
              <span className="text-slate-500">{count}</span>
            </span>
          ))}
          <Badge tone={isExportable ? "good" : "bad"}>
            {isExportable ? "Exportable" : "Blocked"}
          </Badge>
        </div>
      </div>

      {findings.length === 0 ? (
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {emptyMessage}
        </p>
      ) : (
        <div className="space-y-4">
          {Object.entries(grouped).map(([category, categoryFindings]) => (
            <div key={category}>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                {category}
              </h3>
              <ul className="space-y-2">
                {categoryFindings.map((finding, index) => (
                  <li
                    key={`${finding.rule_id}-${index}`}
                    className="flex items-start gap-3 text-sm"
                  >
                    <SeverityBadge severity={finding.severity} />
                    <span className="flex-1">
                      {finding.message}
                      <span className="ml-2 whitespace-nowrap font-mono text-xs text-slate-400">
                        {finding.rule_id}
                      </span>
                      <span className="ml-2 whitespace-nowrap text-xs text-slate-400">
                        · {SOURCE_LABELS[finding.source] ?? finding.source}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {overriddenRuleIds.length > 0 && (
        <p className="mt-4 border-t border-slate-200 pt-3 text-xs text-slate-500 dark:border-slate-800">
          Overridden by a human with a logged reason:{" "}
          <span className="font-mono">{overriddenRuleIds.join(", ")}</span>
        </p>
      )}
    </Card>
  );
}
