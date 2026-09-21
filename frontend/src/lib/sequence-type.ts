/**
 * What kind of transaction the NEXT sequence is, before the filer says
 * otherwise (gap Phase 4c).
 *
 * WHY a default at all, and why this one: the first sequence of a project
 * is the application itself; every later one answers or adds to it. FDA
 * makes the distinction mandatory -- one "application" per regulatory
 * activity, everything after it an "amendment" -- and refuses a second
 * `initial`. Defaulting later sequences to `response` means the common case
 * needs no thought, while the select still lets the filer say something
 * else (an EU `additional-info`, say) when that is what the sequence is.
 *
 * The VALUES come from GET /enums (`submission_unit_type`), never from a
 * list typed here: this function only picks between two of them.
 */
export function defaultSubmissionUnitType(existingSequences: number): string {
  return existingSequences === 0 ? "initial" : "response";
}
