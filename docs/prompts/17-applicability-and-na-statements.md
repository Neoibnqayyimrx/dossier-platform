# P17 — Applicability as data, and the statements it owes

**Before starting:** read `docs/target-toc.yaml` (the `applicability_profile` and `na_statement_generator` capabilities, and every leaf with `applicable: false`), `app/ctd/region_profiles.py`, `app/ctd/structure.py`, `app/ctd/build.py`, and `app/ectd/scaffold.py`. Depends on P16.

## Goal

Unblock **25 leaves** — 14 that owe a not-applicable statement, and 11 more gated behind having applicability be declared rather than assumed. Cheapest phase on the roadmap by a wide margin, and the largest single jump in coverage.

## The problem, stated precisely

The source dossier declares its own scope three times:

- *"As per NAFDAC guidelines for multisource (generic) pharmaceutical products, Modules 2.4–2.7 are not applicable"*
- *"...Module 4 is not applicable"*
- *"...only Module 5.3.1 is applicable"*

Those are not omissions. They are statements the dossier makes, printed in the filed document, in the folder where the module would be. Today this platform expresses them by having nothing there — and an empty `m4` folder and a declared exclusion look entirely different to an assessor. Check `ectd/scaffold.py`, which currently notes there is "nothing to scaffold for the empty m4/m5 module folders": that comment is the gap.

The deeper problem is that applicability is currently implicit in which sections happen to be registered. That works for exactly one submission type. The day a new chemical entity or an FDA filing arrives, Module 4 becomes applicable and there is no switch to flip.

## Tasks

### P17a — Applicability as declared config (backend)

1. **A `SubmissionType` concept**, starting with `MULTISOURCE_GENERIC`. It belongs on `Project`, not `Product`: the same product can be filed generically in one market and differently in another, exactly as `Applicant` is per-filing (see the P15 build-log entry on scope).

2. **An applicability table in the region profile**, keyed by submission type, declaring per section number one of: `REQUIRED`, `CONDITIONAL` (with the condition text), or `NOT_APPLICABLE` (with the guideline citation that makes it so). Populate from `docs/target-toc.yaml` — the `applicable`, `condition` and `not_applicable_reason` fields are already there, and duplicating them by hand would create two truths.

   Keep this beside `module1_slots` in `region_profiles.py`, for the reason already recorded there: region rules live in config because regulatory formats change and must be re-confirmed against the agency's current requirements.

3. **A statement renderer** — one template, filled with the section number, its title, and the citation. Registered like any other section so assembly, folder placement, TOC and the eCTD backbone all pick it up without special-casing. Resist a separate emit path for statements; a second pipeline is a second thing to keep in sync.

4. **Folder placement** for `2.4`–`2.7`, `4.0`, `5.3.2`–`5.3.7`, `3.2.P.4.6` and `3.2.A` in `MODULE_2_5_FOLDERS`. Module 4 gets one statement covering 4.1–4.3 rather than three; the source dossier does the same.

5. **A validation rule**: a section marked `NOT_APPLICABLE` that nonetheless has content is an ERROR, and a `CONDITIONAL` section whose condition is unanswered is a WARNING. The second one is what stops a biowaiver claim quietly going missing.

### P17b — Applicability in the browser (frontend)

6. **Show the section list on the project page**, grouped by module, each leaf labelled with its status: produced, placeholder, not applicable, or outstanding. This is the first screen where a user can see what the dossier still owes — right now that information exists only in a terminal.

7. **Answer the conditional questions in the UI.** `CONDITIONAL` leaves (1.2.13 previous market authorization, 1.2.15 CEP, 1.2.16 APIMF letter of access, 1.2.17 and 1.2.18 biowaivers, 3.2.P.4.6 novel excipients, 5.3.1.3 IVIVC) each need a yes/no from the user, stored on the project. Unanswered is a WARNING; answered "no" produces the not-applicable statement automatically.

8. Follow the existing pattern: the wizard's shape is data in `frontend/src/lib/wizard-steps.ts`, and vocabularies come from `GET /enums`. Do not hard-code the section list in the frontend — serve it from the backend so it cannot drift from the region profile.

## Definition of done

- `scripts/check_target_toc.py` reports roughly **20+/98**, up from 6.
- A built package contains a readable statement leaf in `m4`, not an empty folder.
- `tests/` covers: a not-applicable section renders its statement; a conditional section answered "no" renders one; answered "yes" does not; an unanswered condition raises a WARNING.
- Switching a project's submission type changes which leaves are required, proven by a test.

## Build log

Record why applicability is a project-level property and not a product-level one, and the alternative rejected. That distinction is the one a future contributor will get wrong.
