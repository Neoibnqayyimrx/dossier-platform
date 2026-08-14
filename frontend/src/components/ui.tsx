/**
 * The small shared vocabulary of visual pieces this app repeats.
 *
 * WHY hand-rolled instead of a component library: the whole UI is a
 * handful of screens made of cards, badges and buttons. Pulling in a
 * design system would add a dependency and a theme layer to style five
 * primitives. Revisit if the surface grows past what one file can hold.
 */

import type { Severity } from "@/lib/types";

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`}
    >
      {children}
    </div>
  );
}

export function PageHeading({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && (
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {subtitle}
          </p>
        )}
      </div>
      {actions}
    </div>
  );
}

/**
 * Severity colours are deliberately not a rainbow: ERROR is the only one
 * that blocks an export, so it is the only one that gets red. WARNING and
 * INFO are muted on purpose -- P06's R11 pharmacopoeia reminder fires on
 * every clean dossier, and a screen full of amber would train users to
 * ignore all of it. ADVISORY (the AI reviewer, P10) is visually distinct
 * from every deterministic severity so nobody mistakes a suggestion for a
 * finding.
 */
const SEVERITY_STYLES: Record<Severity, string> = {
  ERROR:
    "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300 ring-red-600/20",
  WARNING:
    "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300 ring-amber-600/20",
  INFO: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 ring-slate-500/20",
  ADVISORY:
    "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300 ring-violet-600/20",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${SEVERITY_STYLES[severity]}`}
    >
      {severity}
    </span>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "good" | "bad";
}) {
  const tones = {
    neutral:
      "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 ring-slate-500/20",
    good: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 ring-emerald-600/20",
    bad: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300 ring-red-600/20",
  };
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300"
    >
      {message}
    </div>
  );
}
