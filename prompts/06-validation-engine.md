# P06 — Deterministic Validation / Rule Engine (the "regulatory intelligence")

**Before starting:** read `AGENTS.md` (§5). Depends on P01–P02 (needs the data model + readiness endpoint stub). This is where the platform earns the word "intelligence" — and it must be **deterministic**, not LLM-based.

## Goal

Run hundreds of cross-field consistency and completeness checks over a project's structured data (and, later, its documents), producing a pass/warn/fail report that gates export.

## Design

- A **rule** is a small, testable unit: `id`, `severity` (error/warning/info), `category`, a `check(project) -> Result`, and a human-readable message with the offending values.
- Rules are **registered** in a registry so P02's `/readiness` endpoint and the builders can run the full suite.
- Rules operate on the **structured data** (deterministic). The LLM-based "AI reviewer" is a *separate, additive* layer in P10 that flags softer issues — it never replaces these rules and is never the source of truth.

## Tasks

1. **Rule framework** (`services/validation/engine.py`): registry, `Severity`, `RuleResult`, `run_all(project) -> Report`. Report aggregates by severity and category.
2. **Implement an initial rule set** covering at least:
   - **Consistency:** declared shelf life ≤ duration supported by long-term stability data (this catches the deliberate 36-vs-24 seed inconsistency); product strength matches strength stated on label/packaging; pack size matches artwork/packaging entries; API manufacturer referenced exists; API specification present; composition percentages total to ~100%.
   - **Completeness:** required entities present for the registration type (e.g. bioequivalence required and included for a generic); GMP status present and not expired; required certificates present and unexpired.
   - **Reference integrity:** every manufacturer/API/excipient referenced by a document actually exists in the data.
   - **Regulatory limits (data-level):** residual solvent limits flagged against ICH Q3C class limits (encode the class limits as data); pharmacopoeial version references flagged as "verify current version" (do NOT embed pharmacopoeia text — just flag for human check).
3. **Region-aware rules:** rules can declare which region profiles they apply to (NAFDAC/FDA/EU). The runner filters by the project's region.
4. **Wire `/projects/{id}/readiness`** (from P02) to return the real report.
5. **Export gate:** expose `is_exportable(project)` = no unresolved `error`-severity results (warnings allowed; errors block unless a human override with a logged reason exists).
6. **Tests**: the seed demo project fails the shelf-life rule with the exact expected message; a corrected fixture passes; region filtering excludes non-applicable rules; the export gate blocks on an error and allows on override.

## Definition of done

- Running validation on the demo project produces a structured report that catches the seeded shelf-life inconsistency and any missing required items.
- `/readiness` returns the report; export is gated on zero unresolved errors.
- Each rule has a unit test with a passing and a failing fixture.

## Design notes

- Keep rules small and independently testable — this suite will grow to hundreds. A big monolithic validator is a smell.
- Messages must name the offending values ("shelf life 36 months exceeds 24 months supported by long-term study S-002"), not just say "inconsistent".

## On completion

Tick **P06** in `AGENTS.md` §7; append to `reference/build-log.md` with the rule count and categories.
