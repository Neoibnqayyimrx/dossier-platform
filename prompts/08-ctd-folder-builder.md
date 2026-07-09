# P08 — CTD / NAPAMS Folder + TOC Builder (the MVP output)

**Before starting:** read `AGENTS.md` (§2 target #1) and `/reference/nafdac-vs-fda-ema-scope.md`. Depends on P04–P07. **This is the first genuinely shippable deliverable** — a NAFDAC-ready CTD package. No XML backbone here.

## Goal

Assemble the leaf inventory (P07) into a correctly-structured **CTD folder tree** with a generated table of contents and the NAFDAC/NAPAMS Module 1 documents, packaged as a ZIP ready for portal upload.

## Tasks

1. **CTD folder map** (`services/ctd/structure.py`): the canonical Module 1–5 folder hierarchy and section numbering (ICH M4 for Modules 2–5; NAFDAC-specific Module 1). Region profile = `NAFDAC`. Keep Module 1 structure in the **region profile config**, not hard-coded, so FDA/EU profiles can be added later.
2. **Placement engine** (`services/ctd/build.py`): place each leaf PDF from the inventory into its correct folder/filename per the map. Filenames follow a consistent, documented convention.
3. **Nigeria Module 1 assembly:** cover letter (to the Director-General), application information, registration forms, certificates, trademark, licences, administrative declarations — driven by the data model + templates (P04). Where a document is an uploaded certificate rather than generated, place the uploaded file (from object storage) into the right slot.
4. **TOC / navigation builder** (`services/ctd/toc.py`): generate a table of contents (and, if useful, a hyperlinked index PDF/HTML) reflecting the actual placed documents, with section numbers, titles, and page/document references. Regenerate deterministically whenever the set of documents changes.
5. **Packager**: zip the tree into a submission package; include a manifest listing every file with its MD5 (useful for the applicant and for later eCTD reuse).
6. **Gate on validation** (P06): refuse to build/export if unresolved errors exist.
7. **API**: `POST /projects/{id}/build/ctd` → produces and stores the ZIP, returns a download handle + manifest.
8. **Tests:** the demo project (once its shelf-life inconsistency is resolved or overridden) builds a complete CTD ZIP; the tree matches the expected NAFDAC structure; the TOC lists every placed document; the manifest MD5s match the files.

## Definition of done

- A project builds to a NAFDAC-structured CTD ZIP with correct Module 1–5 folders, placed leaf PDFs, a generated TOC, and a manifest.
- Build is blocked when validation has unresolved errors.
- Structure and Module 1 come from the region profile config, not hard-coding.

## Why this ships alone

Per the scope reference, NAFDAC accepts a CTD via the NAPAMS portal with no XML backbone. This package is directly usable. Everything after this (P09+) is for FDA/EU eCTD and is strictly additive.

## On completion

Tick **P08** in `AGENTS.md` §7; append to `reference/build-log.md`. **This is a good point to demo the platform end-to-end.**
