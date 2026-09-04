# P24 — Derived documents, and closing the target

**Before starting:** read `docs/target-toc.yaml` in full — this phase closes what remains — plus `app/ctd/toc.py`, `app/templating/registry.py` entry for 2.3, and `backend/templates/section_2_3_qos.docx`. Depends on P17 through P23. This is the last planned phase before the target is complete.

## Goal

Build the documents that are *derived from other documents*, and close out whatever the coverage check still reports missing. At the end of this phase, `scripts/check_target_toc.py --strict` should exit 0.

## Why these are last

A table of contents, a Quality Information Summary and a Quality Overall Summary are all re-presentations of content that lives elsewhere. They can only be built once that content exists — and building them earlier would mean writing them by hand, which is the failure mode.

## Tasks

### P24a — Per-module tables of contents

1. **Generate 1.1, 2.1, 3.1 and 5.1** by walking the leaves actually present in the built package. `ctd/toc.py` already generates a TOC; extend it to emit one per module. A TOC derived from the real tree cannot disagree with the tree — a hand-written one always eventually does.

2. **Include not-applicable statements in the TOC.** They are leaves and an assessor expects to find them listed, not silently absent.

### P24b — The Quality Information Summary (1.4.2)

3. **The highest-leverage generated document in the target.** The QIS is almost entirely a re-presentation of Module 3 in NAFDAC's own layout — exactly the document that goes wrong when a human retypes Module 3 into a form. Every field must be sourced from the same data the Module 3 sections render from. Not one field re-entered.

4. **A test proving it cannot diverge from Module 3.** If any QIS field can be authored independently, that field is a defect.

### P24c — The Quality Overall Summary, in full (2.3)

5. **2.3 is registered but thin.** The target lists fourteen subsections under it — 2.3.S.1 through 2.3.S.7 and 2.3.P.1 through 2.3.P.7 — each mirroring a Module 3 section. Build the QOS by assembling from the same data those sections render from, with narrative slots only where genuine summary judgement is required.

6. **A QOS that can drift from Module 3 is the defect this platform exists to eliminate.** Test that it cannot: change a value in Module 3, assert the QOS changes with it.

### P24d — Remaining hybrid sections

7. **Work the list.** Whatever `scripts/check_target_toc.py` still reports — the 3.2.S.2.x process description group, 3.2.P.2.x pharmaceutical development, 3.2.P.3.3 and 3.2.P.3.4, the justification-of-specification leaves, 3.3 and 5.4 literature references, 1.2.1, 1.2.14, 1.5 and 1.6. Each is a template, a context builder, a folder mapping and a narrative slot where prose is genuinely needed.

8. **Resolve the two open questions** flagged in the YAML notes, which need a regulatory answer rather than a technical one:
   - 1.2.1 "Application form" and 1.2.2 "Registration form" appear as separate items in the source dossier. Confirm against NAFDAC's current form set whether these are two documents or one, and record the finding.
   - 1.6 "Samples" refers to physical samples, not a document. Confirm what the dossier owes in that folder.

9. **Fix the numbering drift.** The registry registers the registration form as `"1.2"`, but 1.2 is a heading and the document is 1.2.2. Renumber the registry entry and its region-profile slot.

### P24e — Turn the gate on

10. **Switch CI to `--strict`.** From this point a leaf with no route to production fails the build. The check stops being a progress report and becomes a contract.

11. **Full end-to-end proof.** Seed a complete realistic product — the Amlodipine 5 mg worked example the target was derived from is the obvious candidate — fill every collection, attach every uploaded document, build, and validate the resulting package against `reference/ectd_dtd/ich-ectd-3-2.dtd`. Record the leaf count and compare it to 98.

## Definition of done

- `scripts/check_target_toc.py --strict` exits 0.
- A complete dossier builds from the browser with no terminal or database access.
- Tests prove the QIS, the QOS and every TOC cannot disagree with the data they derive from.
- The README coverage line reads 98/98.

## Build log

This is the entry worth writing carefully. Record what the 98-leaf target got wrong — every place the YAML proved inaccurate against the real regulatory requirement, because that is the file every future submission type will be derived from.
