/**
 * Is a 90 % confidence interval inside the acceptance window? -- the
 * browser's copy.
 *
 * ## Why this exists at all, given the backend already does it
 *
 * The same claim `src/lib/acceptance.ts` makes for specification limits,
 * and it is stronger here. A filer transcribing a bioequivalence result is
 * copying six numbers off one page of a CRO's report, and a digit
 * transposed in a confidence interval is the difference between a study
 * that supports an approval and one that does not. Seeing "OUTSIDE the
 * window" appear as the cell loses focus, with the report still open, is
 * worth more than the same finding arriving at export three days later.
 *
 * ## Why the duplication is acceptable, on the same two conditions
 *
 *   1. **This copy is advisory and cannot gate anything.** The export gate
 *      is rule R25 on the backend. If this is wrong in the permissive
 *      direction the build still blocks; if it is wrong in the strict
 *      direction the filer sees a warning the validation report does not
 *      repeat. Neither can put a bad number in a package.
 *   2. **The window is not hard-coded here.** It is a regulatory parameter
 *      that lives in the backend's region profile
 *      (`app/ctd/region_profiles.py::BioequivalenceWindow`), and it is
 *      passed in. This module knows how to COMPARE, not what the limit is
 *      -- which is the half that changes when an agency republishes a
 *      table.
 */

export interface AcceptanceWindow {
  lower: number;
  upper: number;
}

/**
 * The ICH/WHO window every region starts from. Exported as a fallback for
 * a screen that has not been told the project's region yet, and labelled
 * as such: a screen showing NO window would silently check nothing.
 */
export const DEFAULT_WINDOW: AcceptanceWindow = { lower: 80, upper: 125 };

/** The tighter window for a narrow-therapeutic-index drug. */
export const NARROW_THERAPEUTIC_INDEX_WINDOW: AcceptanceWindow = {
  lower: 90,
  upper: 111.11,
};

export function windowFor(narrowTherapeuticIndex: boolean): AcceptanceWindow {
  return narrowTherapeuticIndex ? NARROW_THERAPEUTIC_INDEX_WINDOW : DEFAULT_WINDOW;
}

/** "80.00 - 125.00 %" -- the way a guideline writes it, and the way the
 * BTI form prints it. Two decimals because the window itself is stated to
 * two, and a bound of 80.0 printed against a limit of 80 invites the
 * reader to wonder which way 79.996 was rounded. */
export function describeWindow(w: AcceptanceWindow): string {
  return `${w.lower.toFixed(2)} - ${w.upper.toFixed(2)} %`;
}

/**
 * Which bounds of an interval fall outside the window.
 *
 * Returns the bound NAMES, not a boolean, for the reason the backend's
 * `BioequivalenceResult.outside` does: a low lower bound and a high upper
 * bound are different problems with the same product, and the filer needs
 * to be told which.
 *
 * A bound that is not a finite number is NOT reported as breaching. An
 * empty or half-typed cell is a cell nobody has finished, and flagging it
 * red while the filer is still typing teaches them to ignore the flag --
 * the failure mode an advisory check must never have. `null` from
 * `verdictFor` below is the honest third state, and it never means "passed".
 */
export function outsideBounds(
  lower: number | null,
  upper: number | null,
  w: AcceptanceWindow,
): Array<"lower" | "upper"> {
  const breached: Array<"lower" | "upper"> = [];
  if (lower !== null && Number.isFinite(lower) && lower < w.lower) breached.push("lower");
  if (upper !== null && Number.isFinite(upper) && upper > w.upper) breached.push("upper");
  return breached;
}

export type IntervalVerdict = "within" | "outside" | null;

/**
 * The verdict for one parameter's interval.
 *
 * `null` means "not decidable yet" -- a bound is missing or unparseable --
 * and is a third state, never a pass. Same discipline as
 * `acceptance.ts::evaluate` and the backend's `meets_criterion`.
 */
export function verdictFor(
  lower: number | null,
  upper: number | null,
  w: AcceptanceWindow,
): IntervalVerdict {
  if (lower === null || upper === null) return null;
  if (!Number.isFinite(lower) || !Number.isFinite(upper)) return null;
  return outsideBounds(lower, upper, w).length === 0 ? "within" : "outside";
}

/**
 * Parse a bound the filer typed. Returns `null` for anything that is not a
 * number, which flows through `verdictFor` as "not decidable" rather than
 * as zero -- reading an empty cell as 0 would report every blank interval
 * as failing its lower bound.
 */
export function parseBound(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  // A comma decimal separator is what a European keyboard and a European
  // CRO's report both produce, and treating "95,80" as unparseable would
  // leave a real interval unchecked.
  const value = Number(trimmed.replace(",", "."));
  return Number.isFinite(value) ? value : null;
}
