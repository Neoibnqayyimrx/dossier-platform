/**
 * Does a result meet its acceptance criterion? -- the browser's copy.
 *
 * ## Why this exists at all, given the backend already does it
 *
 * P20's brief: "Show out-of-specification results immediately, at entry,
 * rather than at export. Catching it at the point of typing is worth more
 * than catching it at build." That is a real claim about how the work
 * goes -- the person entering a certificate of analysis has the paper in
 * front of them, and can check a transcription error in five seconds. The
 * same finding surfacing at export, days later, is a hunt.
 *
 * ## Why the duplication is acceptable HERE and nowhere else
 *
 * It is duplication, and duplication of a rule is normally exactly what
 * this platform refuses (AGENTS.md §5 -- the determinism boundary exists
 * so a number has one source). Two things make it tolerable:
 *
 *   1. **This copy is advisory and cannot gate anything.** The export gate
 *      is `Report.is_exportable()` on the backend, reading R22. If this
 *      file is wrong in the permissive direction, the backend still blocks
 *      the build; if it is wrong in the strict direction, the filer sees a
 *      warning the validation report does not repeat. Neither can put a
 *      bad number in a package.
 *   2. **It is pinned to its Python original by a shared test table.** The
 *      cases in `acceptance.test.ts` are the cases in the backend's
 *      `test_acceptance_criteria_are_read_the_way_a_pharmacist_reads_them`,
 *      deliberately the same list, so a change to one that is not made to
 *      the other fails a test rather than drifting quietly.
 *
 * If a third copy is ever wanted, that is the signal to expose the check
 * as an endpoint instead.
 *
 * Mirrors backend/app/validation/acceptance.py. Read that file's docstring
 * for the reasoning about failure direction -- the short version is that
 * every branch here returns `null` rather than guessing, and **`null`
 * never means "passed"**.
 */

const NUMBER = String.raw`[-+]?\d+(?:[.,]\d+)?`;

const RANGE_RE = new RegExp(
  `(${NUMBER})\\s*(?:[-‐-―]|to)\\s*(${NUMBER})`,
  "i",
);
const MAX_RE = new RegExp(
  `(?:nmt|not\\s+more\\s+than|max(?:imum)?|below|<=|<|≤)\\s*(${NUMBER})`,
  "i",
);
const MIN_RE = new RegExp(
  `(?:nlt|not\\s+less\\s+than|min(?:imum)?|>=|>|≥)\\s*(${NUMBER})`,
  "i",
);
const RESULT_NUMBER_RE = new RegExp(NUMBER);

// The negative list is checked FIRST and is the more literal of the two:
// "does not comply" contains "comply", so a substring test in the wrong
// order reads a failure as a pass -- the single most dangerous bug this
// file could have.
const NON_CONFORMING = [
  "does not comply",
  "does not conform",
  "not complies",
  "non-compliant",
  "noncompliant",
  "fails",
  "failed",
  "fail",
  "out of specification",
  "oos",
];
const CONFORMING = [
  "complies",
  "conforms",
  "conform",
  "corresponds",
  "passes",
  "passed",
  "pass",
  "satisfactory",
];

export interface NumericLimit {
  low: number | null;
  high: number | null;
}

function toNumber(text: string): number {
  // A European decimal comma must not read as a hundredfold error: "0,15"
  // is fifteen hundredths, not fifteen.
  return Number.parseFloat(text.replace(",", "."));
}

export function parseLimit(criterion: string): NumericLimit | null {
  if (!criterion) return null;

  // A range is tried first: "90.0 - 120.0 %" also matches the one-sided
  // patterns in some spellings, and reading a range as a single bound
  // would silently drop half the limit.
  const range = RANGE_RE.exec(criterion);
  if (range) return { low: toNumber(range[1]), high: toNumber(range[2]) };

  const high = MAX_RE.exec(criterion);
  const low = MIN_RE.exec(criterion);
  if (!high && !low) return null;
  return {
    low: low ? toNumber(low[1]) : null,
    high: high ? toNumber(high[1]) : null,
  };
}

export function parseResult(result: string): number | null {
  if (!result) return null;
  // The FIRST number: "0.12 % (RRT 0.8)" means its first number -- the
  // trailing ones are units and identifiers, not the measurement.
  const match = RESULT_NUMBER_RE.exec(result);
  return match ? toNumber(match[0]) : null;
}

export function qualitativeVerdict(result: string): boolean | null {
  const text = result.toLowerCase();
  if (NON_CONFORMING.some((token) => text.includes(token))) return false;
  if (CONFORMING.some((token) => text.includes(token))) return true;
  return null;
}

/**
 * `true` = meets the criterion, `false` = does not, `null` = cannot be
 * decided here.
 *
 * The three outcomes are genuinely three. A caller that treats `null` as a
 * pass has thrown away the distinction between "checked and fine" and
 * "nobody checked".
 */
export function evaluate(criterion: string, result: string): boolean | null {
  // A stated non-conformance outranks the numbers: a result reading
  // "Fails" against a range is out of specification, and having no
  // parseable number in it must not rescue it.
  const verdict = qualitativeVerdict(result);
  if (verdict === false) return false;

  const limit = parseLimit(criterion);
  if (limit) {
    const value = parseResult(result);
    if (value === null) return verdict ? true : null;
    if (limit.low !== null && value < limit.low) return false;
    if (limit.high !== null && value > limit.high) return false;
    return true;
  }

  return verdict;
}
