# P16 — The target TOC as the contract

**Before starting:** read `docs/target-toc.yaml` in full, then `backend/scripts/check_target_toc.py`, `app/templating/registry.py`, and `app/ctd/region_profiles.py`. Small phase, but everything from P17 onward is measured by it.

## Goal

Make "what a complete dossier is" a piece of data this repo checks on every push, rather than prose someone re-interprets each time they audit.

## Context

`docs/target-toc.yaml` was derived leaf-by-leaf from a real filed NAFDAC multisource dossier (Me Cure, Amlodipine Tablets 5 mg). 98 leaves. It declares, per leaf: whether it is applicable, how it is produced (`generated` / `hybrid` / `uploaded` / `na_statement` / `toc`), what it repeats over, and which capability blocks it.

`scripts/check_target_toc.py` compares that target against what the platform can actually produce. It currently reports **6/98**.

Two defects in the checker have to be fixed before that number can be trusted.

## Tasks

1. **The import path defect.** Run as `python scripts/check_target_toc.py`, Python puts `scripts/` on `sys.path` instead of `backend/`, `app` fails to import, and every status silently resolves to `unknown` — a report that has checked nothing but does not say so. Pin `backend/` onto `sys.path` at the top of the script so the invocation style cannot change the answer.

2. **The single-source defect.** `registered_keys()` reads only `templating.registry.SECTIONS`. Module 1 documents are not produced that way — they come from `region_profiles.NAFDAC_PROFILE.module1_slots` plus the `templating/certificates.py` and `templating/declarations.py` renderers. So 1.2.4, 1.2.5 and 1.2.6 report `missing` when they genuinely render, and the certificate slots report `missing` when they have folder placement and a placeholder path.

   Rename it `producible_keys()` and union both sources. Where a leaf is `production: uploaded` and a slot exists but no file does, the correct status is `placeholder`, not `done` — that distinction is the whole point, and a check that credits a placeholder as a finished document would launder the platform's largest gap into a green tick.

3. **Fail loudly on an unresolvable check.** If the registry cannot be imported, raise rather than returning `unknown` for all 98 leaves. A check that reports universal ignorance while exiting 0 is worse than no check.

4. **Wire it into `.github/workflows/ci.yml`**, alongside ruff and black. Without `--strict` for now: it exits 1 on any gap, which today means every build fails, and a permanently red build teaches everyone to ignore it. Add a comment saying `--strict` gets switched on when coverage approaches complete, at which point the report becomes a gate.

5. **Print the coverage line in a form that can be pasted into the README** — `6/98 leaves` — so progress is visible outside the terminal.

## Definition of done

- `uv run python scripts/check_target_toc.py` and `uv run python -m scripts.check_target_toc` produce identical output.
- Module 1 credits the declarations that genuinely render; certificate slots read `placeholder`, not `missing`.
- CI runs the check on every push.
- A test asserts that every `blocked_by:` value in the YAML names a key that exists in the `capabilities:` block. A typo'd blocker silently unblocks a leaf otherwise.

## Do not

Do not edit `status:` values in the YAML by hand. `status` is computed by the script; a hand-maintained status column is a status column that lies. The fields humans own are `applicable`, `production`, `repeat`, `data_sources`, `blocked_by` and `notes`.

## Build log

Record the starting coverage number. Every phase after this one is measured as a delta against it.
