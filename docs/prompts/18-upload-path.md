# P18 — The upload path

**Before starting:** read `docs/target-toc.yaml` (the `upload_path` capability and all 22 leaves that name it), `app/models/certificate.py` including its docstring, `app/core/storage.py`, `app/api/routers/artifacts.py`, `app/assembly/assemble.py`, and `app/ectd/leaf.py`. Depends on P16. Independent of P17 — either order works, but P17 is cheaper.

## Goal

Unblock **22 leaves** and change what this platform is. Today it can build a structurally perfect eCTD package in which roughly a quarter of the leaves are placeholders. This phase is what makes the output submittable rather than demonstrable.

## The problem, stated precisely

Roughly a quarter of a real dossier consists of artifacts the platform cannot author: a regulator's Certificate of Pharmaceutical Product, a contract lab's analytical method validation report, a CRO's bioequivalence study report, an API manufacturer's spectral characterisation data.

`Certificate` is metadata only — type, issuing authority, number, issue and expiry dates. Its own docstring is candid about the consequence: it exists so the build "can emit a clearly-marked placeholder document at the right path". That was the right call at the time. It is now the largest gap in the platform.

MinIO storage exists, but only builders write to it. `artifacts.py` is download-only, and correctly scopes reads to the project's own prefix. There is no route by which a regulatory affairs officer attaches a real file.

## Tasks

### P18a — Documents as first-class leaves (backend)

1. **A `SectionDocument` model**: section number, subject slug (for sections repeated per drug substance), storage key, md5, original filename, content type, size, uploader, uploaded at, and project FK. Keyed by *section instance*, not section number — `app/templating/instances.py` already establishes why: "3.2.S.1" does not name one document once a product has two actives, and an uploaded characterisation report belongs to one substance.

2. **An upload endpoint**, scoped to the project and owner-checked like every other route. Reuse the authorization reasoning already written in `artifacts.py`: the storage key must be constructed server-side under `projects/{project_id}/`, never accepted from the client.

3. **Assembly iterates rendered ∪ uploaded ∪ placeholder.** `assemble_project` currently walks `templating.registry.SECTIONS` only. It must walk the full instance list, and for each decide the source. Preserve the P07 rule recorded in that module: one leaf per section, never a merged mega-PDF. An uploaded PDF is already a leaf — checksum the real bytes, do not re-render it.

4. **Non-PDF uploads.** Users will attach `.docx` and scans. Decide and record: convert to PDF at upload, at assembly, or reject non-PDF. Whatever the choice, the md5 in the manifest must be over the bytes that ship in the package, or the eCTD checksums are wrong.

5. **The rule that makes placeholders honest.** An applicable leaf still standing on a placeholder at export time is an `ERROR` that blocks the build. This is the severity model working as designed — a placeholder is precisely "we know this is missing", and shipping it silently is the failure mode. Existing certificate rules (R13 and friends) should be rephrased in terms of "has a document", not "has a metadata row".

6. **Certificate types missing from the enum**, found against the target: certificate of incorporation (1.2.3), superintendent pharmacist's annual licence to practice (1.2.11), certificate of registration and retention of premises (1.2.12). Add them with a migration.

### P18b — Attaching files in the browser (frontend)

7. **An upload control on each leaf** in the section list built in P17: drop a file, see filename, size and upload date, replace it, remove it. A leaf awaiting a file must look visibly different from one that is done.

8. **A "what's still missing" view** listing every applicable leaf without a document, because that list is the actual working checklist for the person assembling the submission. It is the screen they will keep open.

9. **Show the block plainly.** When export is refused, say which leaves caused it and link straight to each — not a generic 409. `OverridePanel` already handles the deliberate-exception path; this is the ordinary path, and it should be the easier one.

## Definition of done

- `scripts/check_target_toc.py` shows the 22 `upload_path` leaves moving from `placeholder`/`missing` to `done` once files are attached.
- A test proves a package containing an uploaded PDF has a manifest md5 matching the shipped bytes.
- A test proves export is blocked while an applicable leaf holds a placeholder, and passes once a document is attached.
- A test proves one project cannot read another's uploaded documents.
- End to end in the browser: create a product, fill the wizard, attach the required certificates, build, download.

## Build log

Record the non-PDF decision and why. Record whether uploaded documents are versioned or replaced in place — and if replaced, that this is a deliberate simplification, since a regulatory audit trail will eventually want the history.
