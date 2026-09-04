# P19 — The sections your data already supports

**Before starting:** read `docs/target-toc.yaml` (the `repeat_axis_generalisation` capability and every leaf marked `DATA READY` in its notes), `app/templating/instances.py` in full, `app/templating/registry.py`, `app/ctd/structure.py`, and the models `batch_formula.py`, `packaging.py`, `manufacturer.py`, `excipient.py`. Depends on P16.

## Goal

Register the Module 3 sections whose data is **already modelled and already validated** but which have no `SectionSpec` — and generalise section repetition so they can exist correctly. Cheap coverage, and it exercises the repeat machinery before the harder phases lean on it.

## The problem, stated precisely

The data model is ahead of the section registry. `BatchFormulaLine` already backs the composition table in 3.2.P.1 and the `salt_base_batch_arithmetic` rule, but 3.2.P.3.2 Batch Formula — a section that is literally that table — does not exist. `Packaging` backs `pack_size_matches_packaging`, but 3.2.P.7 does not exist. `Manufacturer` is fully modelled; 3.2.S.2.1 and 3.2.P.3.1 do not exist.

The blocker is not data. It is that `instances.py` repeats along exactly one axis. Its docstring explains the case that forced it — 3.2.S is repeated per drug substance, so AMPICLOX needs two copies — and it hard-codes `REPEAT_PER_DRUG_SUBSTANCE`. But 3.2.P.4.1 repeats per excipient, 3.2.P.3.1 per manufacturing site, and 3.2.P.7 per pack.

## Tasks

### P19a — Generalise the repeat axis (backend)

1. **Make the repeat axis a field on `SectionSpec`**, not a module-level constant: `repeat: str | None` naming the collection to expand over. `instances.py` then resolves the axis generically instead of branching on drug substance.

   Keep every property the existing implementation earned: the subject's *name* in the key and folder rather than a bare index, because an assessor must be able to tell which substance or pack a folder holds without opening it, and because those strings end up in MD5-checksummed paths that must be byte-identical across rebuilds. `slugify_subject` applies unchanged to the new axes.

2. **Folder placement for the new axes.** `DRUG_SUBSTANCE_FOLDERS` is the pattern; excipients and packs need the equivalent. Preserve the raise-on-miss behaviour — the docstring's reasoning holds for every axis: a section with no folder mapping should fail loudly at build time rather than silently land somewhere no reviewer would look.

3. **Register the data-ready sections**, each with a `SectionSpec`, a folder mapping, a `.docx` template and a context builder:
   - **3.2.P.3.2** Batch formula — the cheapest leaf in the target
   - **3.2.P.7** Container closure system (drug product), repeated per pack
   - **3.2.S.2.1** Name and address of API manufacturer, per drug substance
   - **3.2.P.3.1** Manufacturer (drug product), per manufacturing site
   - **3.2.S.5** and **3.2.P.6** Reference standards
   - **3.2.S.6** Container closure system (drug substance)
   - **3.2.R** Regional information — belongs in the region profile, not the common table, since it is region-specific by definition

4. **Do not let one `Packaging` model silently serve both 3.2.S.6 and 3.2.P.7.** How an API is shipped and stored is not how the finished product is packed. Add an explicit role, or separate the models, and record the choice.

5. **3.2.P.4.5** Excipients of human or animal origin — a TSE/BSE statement generated from an origin field on `Excipient` that does not yet exist. Add the field, and a rule: an excipient of animal origin with no supporting certificate is an ERROR.

### P19b — The wizard keeps up (frontend)

6. **Extend `wizard-steps.ts`** for the new fields — excipient origin, packaging role, manufacturing site role. The file's own docstring is the instruction: adding a field should be a one-line edit there, not another bespoke form.

7. **Show repeated sections as repeated** in the section list. A product with two actives owes two copies of 3.2.S.1, and the UI should say so rather than showing one row.

## Definition of done

- `scripts/check_target_toc.py` gains roughly 8–10 leaves.
- A test proves a two-active product produces two instances of each per-substance section, and a three-pack product three instances of 3.2.P.7, with distinct folders.
- A test proves two consecutive builds of the same project produce byte-identical paths and checksums.
- The rendered batch formula reconciles with 3.2.P.1's composition table — same data, so a test should assert they cannot disagree.

## Build log

Record what broke when the repeat axis generalised. The drug-substance implementation encoded assumptions that only became visible under a second axis, and those are worth naming.
