import { describe, expect, it } from "vitest";

import { evaluate } from "@/lib/acceptance";

/**
 * These cases are DELIBERATELY the same list as the backend's
 * `test_acceptance_criteria_are_read_the_way_a_pharmacist_reads_them`
 * (backend/tests/test_control_sections.py).
 *
 * That is the whole mechanism keeping the browser's copy of the acceptance
 * check honest against the Python original: a change made to one and not
 * the other fails here rather than drifting quietly into a wizard that
 * says a batch is fine while the export gate says it is not. See
 * `src/lib/acceptance.ts` for why a second copy exists at all.
 */
const CASES: Array<[string, string, boolean | null]> = [
  ["98.0 - 102.0 % w/w", "99.4 %", true],
  ["98.0 - 102.0 % w/w", "103.4 %", false],
  ["98.0 - 102.0 % w/w", "97.9 %", false],
  ["NMT 1.0 %", "0.42 %", true],
  ["NMT 1.0 %", "1.4 %", false],
  ["NLT 80 % (Q) in 45 minutes", "94 % in 45 min", true],
  ["NLT 80 % (Q) in 45 minutes", "74 % in 45 min", false],
  ["Complies", "Complies", true],
  // "does not comply" CONTAINS "comply": a naive substring test in the
  // wrong order reads a failure as a pass.
  ["Complies", "Does not comply", false],
  // A stated failure outranks the numbers.
  ["98.0 - 102.0 %", "Fails", false],
  // Neither parseable: undecidable, never "passed".
  ["White to off-white powder", "Slightly yellow powder", null],
  // A European decimal comma must not read as a hundredfold error.
  ["NMT 0,15 %", "0,12 %", true],
  ["NMT 0,15 %", "0,20 %", false],
];

describe("acceptance criteria, read the way a pharmacist reads them", () => {
  it.each(CASES)("%s vs %s", (criterion, result, expected) => {
    expect(evaluate(criterion, result)).toBe(expected);
  });

  it("never reports an unparseable pair as a pass", () => {
    // The failure this whole module is shaped to avoid. `null` is not
    // falsy-equals-fail and not truthy-equals-pass; it is a third answer,
    // and the UI has to render it as "not checked".
    expect(evaluate("Conforms to the reference chromatogram", "See attached")).toBeNull();
  });
});
