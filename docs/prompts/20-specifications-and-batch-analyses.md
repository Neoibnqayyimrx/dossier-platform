# P20 — Specifications everywhere, batch analyses, impurities

**Before starting:** read `docs/target-toc.yaml` (`spec_polymorphic_owner`, `batch_analysis_model`, `impurity_model`), `app/models/specification.py`, `app/seed/specifications.py`, the P13 entry in `reference/build-log.md`, and `frontend/src/components/SpecificationEditor.tsx`. Depends on P19.

## Goal

Unblock **9 leaves** across control of the drug substance, the drug product and the excipients — and remove a modelling constraint that will otherwise force a duplicate table.

## The problem, stated precisely

`SpecificationTest` is foreign-keyed to `active_ingredient`. It is therefore drug-substance-only *by construction*.

But a specification is the same artifact wherever it appears: a list of tests, each with a method, an acceptance criterion and a sort order. 3.2.P.5.1 (drug product) and 3.2.P.4.1 (excipients) need exactly that table with a different owner. Building them as separate models means three near-identical tables, three editors, three sets of rules — and the inconsistencies between them are precisely what this platform exists to catch.

Doing this as one migration now is far cheaper than doing it after 3.2.P.5.1 exists separately.

## Tasks

### P20a — One specification, many owners (backend)

1. **Give `SpecificationTest` a polymorphic owner**: drug substance, drug product, or excipient. Choose between a nullable-FK-per-owner-type and a discriminator column with an owner id, and record why — the trade-off is referential integrity against schema churn when a fourth owner type appears. Migrate the existing drug-substance rows without data loss.

2. **Register the sections** with templates, folder mappings and context builders:
   - **3.2.P.5.1** Specification (drug product)
   - **3.2.P.4.1** Specification (excipients), repeated per excipient via P19's axis

3. **A `BatchAnalysis` model**: batch number, manufacture date, batch size, site, and per-test results — each result pointing at the `SpecificationTest` it answers. This is what makes 3.2.S.4.4 and 3.2.P.5.4 generatable rather than typed.

4. **The rule that justifies the whole design**: a batch analysis result outside its own specification's acceptance criterion is an ERROR that names the batch, the test, the result and the limit. Every finding should name the offending values — never just "inconsistent" — as the rules registry already requires.

5. **An `Impurity` model** for 3.2.S.3.2 and 3.2.P.5.5: name, type (process-related, degradation), structure where known, limit, and the monograph or guideline the limit comes from. Wire the existing `pharmacopoeial_version_reminder` rule to reach impurity limits too.

6. **The narrative sections that sit alongside these** — 3.2.S.4.2, 3.2.P.5.2 (analytical procedures), 3.2.S.4.5, 3.2.P.4.4, 3.2.P.5.6 (justifications of specification) — register as `hybrid`, with the specification table rendered from data and a narrative slot for the prose. Where the specification is pharmacopoeial, analytical procedures reduce to a monograph citation; where in-house, a full description. Handle both.

### P20b — One editor, many owners (frontend)

7. **Generalise `SpecificationEditor.tsx`** to take an owner rather than assuming an active ingredient. One editor for all three owner types — the same reasoning as the backend: three editors that drift is the failure mode.

8. **A batch analysis entry screen** where results are entered against the specification's tests, so a result cannot be recorded for a test that is not in the spec. Show out-of-specification results immediately, at entry, rather than at export. Catching it at the point of typing is worth more than catching it at build.

## Definition of done

- `scripts/check_target_toc.py` gains roughly 9 leaves.
- A test proves the same specification model serves all three owner types and renders correctly into each section.
- A test proves an out-of-specification batch result blocks export and names the batch, test, result and limit.
- Existing P13 drug-substance specification tests still pass unchanged — the migration must not regress them.

## Build log

Record the polymorphic-owner decision and the alternative rejected. This is the schema choice most likely to be revisited, so the reasoning needs to be recoverable.
