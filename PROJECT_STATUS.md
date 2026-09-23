# PROJECT STATUS — Technical Audit

**Repo:** `dossier-platform` · **Branch:** `fix/expired-session-and-wizard-preview` · **HEAD:** `8db99fe`
**Audit date:** 2026-09-18 · **Method:** direct inspection of schema, code, tests and executed CLI commands. Claims not verifiable by running something are marked as such.

> **Baseline caveat — read this first.** This audit describes committed state at **`8db99fe`**. While it was running, uncommitted "P25" work appeared in the working tree (a parallel session following `gap.md`) that already addresses several findings below: a `UniqueConstraint("project_id","number")` on `sequence` plus a retry loop in `create_sequence` (fixes 8.3 #6), a frontend CI job running eslint/vitest/build/Playwright (fixes 8.2), and a rewritten README Roadmap (fixes 8.3 #11). Those changes are **not** reflected in the findings below, which describe the committed baseline. The full backend test run below spanned that change, so treat its numbers as baseline-ish, not as a clean measurement of either tree.

**Scope note up front:** this is a NAFDAC-first CTD platform with a working eCTD v3.2.2 backbone bolted on for **EU only**. The two facts most likely to be misread from the README are corrected in §4: (a) the eCTD XML backbone is real and DTD-validated, but `build_ectd_sequence` **raises `NotImplementedError` for any region except EU** (**Phase 4b:** FDA now publishes too; NAFDAC is refused with a message saying it takes CTD); (b) NAFDAC — the default and primary region — ships as a folder-tree ZIP with a generated PDF table of contents and **no XML backbone at all**.

---

## 1. REGULATORY DATA MODEL

### 1.1 Entities that actually exist

All models are SQLAlchemy 2.x declarative, one file per entity under [backend/app/models/](backend/app/models/), re-exported from [models/__init__.py](backend/app/models/__init__.py). Every table inherits [`Base`](backend/app/models/base.py#L18) → UUID PK + `created_at`/`updated_at`.

| Concept | Table | File |
|---|---|---|
| User (auth, role) | `user` | [user.py](backend/app/models/user.py) |
| Applicant (legal filer) | `applicant` | [applicant.py](backend/app/models/applicant.py) |
| Product (master data) | `product` | [product.py](backend/app/models/product.py) |
| Project (= the filing) | `project` | [project.py](backend/app/models/project.py#L30) |
| Section (rendered narrative text) | `section` | [project.py](backend/app/models/project.py#L130) |
| Sequence (`0000`, `0001`…) | `sequence` | [sequence.py](backend/app/models/sequence.py) |
| SequenceLeaf (per-sequence leaf inventory) | `sequence_leaf` | [sequence_leaf.py](backend/app/models/sequence_leaf.py) |
| SectionDocument (uploaded file at a leaf) | `section_document` | [section_document.py](backend/app/models/section_document.py) |
| Manufacturer | `manufacturer` | [manufacturer.py](backend/app/models/manufacturer.py) |
| ActiveIngredient | `active_ingredient` | [active_ingredient.py](backend/app/models/active_ingredient.py) |
| Excipient | `excipient` | [excipient.py](backend/app/models/excipient.py) |
| Packaging | `packaging` | [packaging.py](backend/app/models/packaging.py) |
| BatchFormulaLine | `batch_formula_line` | [batch_formula.py](backend/app/models/batch_formula.py) |
| SpecificationTest | `specification_test` | [specification.py](backend/app/models/specification.py) |
| BatchAnalysis / results | `batch_analysis` (+ results) | [batch_analysis.py](backend/app/models/batch_analysis.py) |
| Impurity | `impurity` | [impurity.py](backend/app/models/impurity.py) |
| StabilityStudy / StabilityResult | `stability_study`, `stability_result` | [stability.py](backend/app/models/stability.py) |
| BioequivalenceStudy / Result / ReferenceProduct / Biowaiver | 4 tables | [bioequivalence.py](backend/app/models/bioequivalence.py) |
| ClinicalEntry | `clinical_entry` | [clinical.py](backend/app/models/clinical.py) |
| Certificate | `certificate` | [certificate.py](backend/app/models/certificate.py) |
| Declaration | `declaration` | [declaration.py](backend/app/models/declaration.py) |
| ProductInformation (SmPC/label/leaflet source) | `product_information` | [product_information.py](backend/app/models/product_information.py) |
| NarrativeGeneration (LLM audit trail) | `narrative_generation` + M2M to `kb_chunk` | [narrative.py](backend/app/models/narrative.py) |
| ValidationOverride | `validation_override` | [validation_override.py](backend/app/models/validation_override.py) |
| KBDocument / KBChunk | `kb_document`, `kb_chunk` | [kb.py](backend/app/models/kb.py) |

### 1.2 Entities that DO NOT exist

- **Organization / Company / Tenant.** Multi-tenancy is a single `owner_id` FK to `user` on `Product` and `Applicant` ([product.py:65](backend/app/models/product.py#L65)). There is no org table, no team, no shared workspace.
- **Application** (the regulatory application a submission belongs to). `Project` is the closest thing, and it is a *product + region + submission type*, not an application number. ~~There is no field for an agency-assigned application/dossier number anywhere.~~ **Phase 4b:** `Project.application_number` and `Project.fda_application_type` now hold it (FDA's backbone needs both), with `Applicant.duns_number` beside them — on `Project` only until Phase 6's `Application` entity exists to receive them.
- **Submission** as distinct from Sequence. `Sequence` is the only transaction entity.
- **Document** as a first-class versioned entity. See §2.
- **DocumentVersion.** Explicitly absent and documented as such: *"WHY there is no version history: replacing an upload overwrites it, both in this row and in object storage"* — [section_document.py:28](backend/app/models/section_document.py#L28).
- **LifecycleOperation as a stored entity.** The operation is a `String(10)` column on `sequence_leaf` ([sequence_leaf.py:45](backend/app/models/sequence_leaf.py#L45)) with no enum, no CHECK constraint, and no FK. Legal values (`new|replace|append|delete`) are enforced only in code at [leaf.py:build_leaf_element](backend/app/ectd/leaf.py#L74).
- **Module.** Modules are not data. They are a hard-coded folder map (§3).

### 1.3 Enforced vs. implied relationships

**Enforced by the database:**
- Every parent/child link is a real `ForeignKey`. Cascades are declared (`cascade="all, delete-orphan"`) on all Project→* and Product→* collections.
- `UniqueConstraint("project_id","section_number","subject_slug")` on `section_document` — [section_document.py:39](backend/app/models/section_document.py#L39). The `subject_slug` defaults to `""` not `NULL` specifically so the constraint actually bites.
- The polymorphic owner for `SpecificationTest`/`BatchAnalysis`/`Impurity` uses **three nullable FKs + a CHECK that exactly one is set** ([spec_owner.py](backend/app/models/spec_owner.py)) — deliberately chosen over a discriminator column so the database can still enforce the owner exists.

**Enforced only in application code (not by the schema):**
- `ActiveIngredient.manufacturer_id` may point at a manufacturer playing the wrong role. The FK proves the row exists; rule **R09** is what proves it is an `API_MANUFACTURER`.
- `Section.number` / `SectionDocument.section_number` are free `String(20)`. Nothing constrains them to a real CTD number — the registry lookup at build time does.
- `SequenceLeaf.operation`, `.modified_file` — no DB-level integrity; verified post-hoc by mechanical checks M07–M09.
- `Project.condition_answers` is a JSON dict keyed by section number. Deliberately un-FK'd ([project.py:52](backend/app/models/project.py#L52)); the keys are owned by config, so the DB cannot police them.
- ~~Sequence numbering (`0000`→`0001`) is computed in the endpoint via `max()`. There is **no unique constraint on `(project_id, number)`** — two concurrent POSTs can produce duplicate sequence numbers.~~ **Fixed in Phase 1:** the number is still computed via `max()` ([projects.py:create_sequence](backend/app/api/routers/projects.py#L147)), but `(project_id, number)` now carries a `UniqueConstraint` (migration `f5c8b21a90d7`), so the database refuses the duplicate and the endpoint retries. This moves from "enforced only in application code" to enforced by the database.

**Migrations:** 22 Alembic revisions in [backend/alembic/versions/](backend/alembic/versions/), single chain from base `b0a8331ddd02`. A test (`tests/test_migration.py`) asserts they apply.

---

## 2. DOCUMENT MANAGEMENT

### 2.1 Created — yes, two distinct paths

1. **Rendered** documents: 72 sections registered in [`SECTIONS`](backend/app/templating/registry.py#L127) (verified: `len(SECTIONS) == 72`), each a `SectionSpec` naming a `.docx` template (38 templates in [backend/templates/](backend/templates/)), rendered by [`render_section`](backend/app/templating/render.py), converted to PDF by [`convert_docx_to_pdf`](backend/app/assembly/pdf.py#L61).
2. **Uploaded** documents: `PUT /projects/{id}/documents/{section_number}` → [ingest.py](backend/app/documents/ingest.py). Accepts PDF and DOCX only (DOCX converted at upload time so the MD5 is settled once), magic-byte checked, 64 MB cap, images explicitly refused.

### 2.2 Versioned — ~~NO~~ **YES (Phase 2)**

~~There is no document version history. Re-uploading overwrites the row and the object-storage bytes.~~ **Closed in Phase 2.** Every upload now appends a `document_version` row with **its own storage key**, so a replacement no longer overwrites its predecessor's bytes. `SectionDocument` stays the current version and keeps its file columns, which is why `assemble.py`, the lifecycle resolver and the validation rules needed no changes at all — see [docs/decisions/0003-document-versioning.md](docs/decisions/0003-document-versioning.md) for why that beat an `is_current` flag, and for the honest statement of what the denormalisation costs.

Two endpoints expose it: `GET /projects/{id}/documents/{section}/versions` (oldest first, `is_current` on each entry) and `.../versions/{n}/content` for a superseded version's bytes. The migration backfills every pre-existing document as its own version 1, keeping its original storage key rather than rewriting history to match the new convention.

The audit's question — *"who changed what before we filed"* — is now answerable.

### 2.3 Tied to a CTD location — YES, and this is the strongest part of the model

A document's identity is `(section_number, subject_slug)` — the `instance_key` property, e.g. `"3.2.S.1-ampicillin"` ([section_document.py:113](backend/app/models/section_document.py#L113)). This matches the rendered-document identity from [instances.py](backend/app/templating/instances.py), so an uploaded leaf and a rendered leaf are addressable identically. Sections that repeat per active ingredient / per excipient / per pack / per manufacturing site are modelled as repeat *axes* on `SectionSpec.repeat`.

### 2.4 Metadata — partial

Present on `SectionDocument`: `storage_key`, `md5`, `size_bytes`, `original_filename`, `content_type`, `uploaded_by_id`, `uploaded_at`.

**Absent:** status, effective date, expiry date, document owner (distinct from uploader), author, review date, document type/class, language, granularity, keywords. `Certificate` carries its own expiry (checked by R13), but that is certificate metadata, not document metadata.

**Lifecycle operation is not document metadata here** — it is derived per build by diffing checksums ([lifecycle.py](backend/app/ectd/lifecycle.py)), never set by a user. There is no way to say "this document replaces that one"; the system infers it.

### 2.5 Approval / workflow state machine — only for LLM prose

The one state machine is `NarrativeStatus` = `PENDING | APPROVED | EDITED` ([enums.py:378](backend/app/models/enums.py#L378)), transitioned by `POST …:approve` / `POST …:edit` ([narrative.py](backend/app/api/routers/narrative.py#L125)). It governs *LLM-generated narrative slots*, not documents.

For documents there is **no status field at all** — no draft/in-review/approved, no reviewer, no sign-off, no e-signature, no 21 CFR Part 11 audit trail. The only auditable human decision in the system is `ValidationOverride` (create + withdraw, both attributed, reason ≥ 20 chars, append-only — [validation_override.py](backend/app/models/validation_override.py)).

---

## 3. DOSSIER / CTD WORKSPACE

### 3.1 Can a tree be assembled? Yes — via API, and it runs

`POST /projects/{id}/build/ctd` → [`build_ctd_package`](backend/app/ctd/build.py#L58) produces a deterministic ZIP: every leaf PDF in its eCTD-style folder, plus a whole-package `toc.pdf` and per-module TOC leaves (1.1, 2.1, 3.1, 5.1) built **from the files actually placed**, not from the plan ([toc.py](backend/app/ctd/toc.py)).

`POST /projects/{id}/build/ectd?sequence_id=…` → [`build_ectd_sequence`](backend/app/ectd/build.py#L98) — ~~EU only~~ EU and FDA since Phase 4b (§4).

There is **no CLI command to build a dossier.** The only CLI entry points are `run_demo.py`, `scripts/seed_demo.py`, `scripts/seed_kb.py`, `scripts/promote_admin.py`, `scripts/check_target_toc.py`, `scripts/make_section_templates.py` (§7). Building goes through HTTP.

### 3.2 Is the CTD structure hard-coded, config-driven, or data? — All three, split by concern

| Concern | Where | Kind |
|---|---|---|
| Which sections exist, their titles, templates, narrative slots, repeat axis | `SECTIONS` dict in [registry.py](backend/app/templating/registry.py#L127) | **Hard-coded Python** (72 entries) |
| Folder path for Modules 2–5 | `MODULE_2_5_FOLDERS` dict in [structure.py](backend/app/ctd/structure.py#L24) | **Hard-coded Python**, raises on a miss |
| Module 1 document list + folders (regional) | `Module1Slot` / `DocumentSlot` lists in [region_profiles.py](backend/app/ctd/region_profiles.py) | **Config dataclasses in Python** |
| Which leaves a submission type owes; applicable / not-applicable / conditional; the guideline citation excusing each | [docs/target-toc.yaml](docs/target-toc.yaml) — 98 leaf entries, loaded by [target_toc.py](backend/app/target_toc.py) | **Data (YAML)** |
| eCTD XML heading placement | `ICH_HEADING_PATH` / `_CHILD_ORDER` in [index_xml.py](backend/app/ectd/index_xml.py#L481) | **Hard-coded Python**, DTD-ordered |

So: *applicability* is data; *structure* is code. Adding a new CTD section means editing three Python files plus the YAML.

### 3.3 Applicability workspace

`GET /projects/{id}/section-status` returns every leaf the project's submission type owes, in CTD order, with its status and (for conditional leaves) the question to answer; `PATCH /projects/{id}/conditions` records yes/no answers and returns the recomputed list ([applicability.py](backend/app/api/routers/applicability.py#L195)). Two submission types are modelled: `MULTISOURCE_GENERIC` and `NEW_CHEMICAL_ENTITY`.

A Next.js frontend exists (8 pages, 15 components — [frontend/src/](frontend/src/)) with a product wizard, section list panel, validation report, override panel, build panel, spec/stability/BE editors.

---

## 4. PUBLISHING ENGINE

### 4.1 What is actually generated

| Output | Status | Evidence |
|---|---|---|
| Deterministic folder-tree ZIP (CTD) | **Works** | [`build_ctd_package`](backend/app/ctd/build.py#L58); fixed 1980-01-01 zip timestamps; byte-identity asserted by `test_the_package_is_a_valid_zip_and_rebuilds_identically` |
| Leaf PDFs, one per section, never merged | **Works** | [`assemble_project`](backend/app/assembly/assemble.py) — one PDF per registered section instance |
| PDF bookmarks | **Works, but one per document** | [`_normalize_pdf`](backend/app/assembly/pdf.py#L128) adds exactly one top-level outline item from the section title. There is **no multi-level bookmark tree inside a leaf**, and no cross-document bookmark/hyperlink generation. |
| Generated table-of-contents PDFs | **Works** | [toc.py](backend/app/ctd/toc.py) — whole-package `toc.pdf` + leaves 1.1/2.1/3.1/5.1 |
| `index.xml` (ICH eCTD 3.2.2 backbone) | **Works, EU + FDA** (Phase 4b) | [`build_index_xml`](backend/app/ectd/index_xml.py#L700) — validates against `reference/ectd_dtd/ich-ectd-3-2.dtd` at build time and **raises** if invalid |
| `index-md5.txt` | **Works** | [`index_md5_line`](backend/app/ectd/checksum.py#L28) — `md5sum`-format, two spaces |
| `m1/eu/eu-regional.xml` | **Works, EU only** | [regional.py](backend/app/ectd/regional.py) — validates against `eu-regional.dtd` |
| `util/dtd/` + `util/style/` scaffold | **Works, EU + FDA** | [scaffold.py](backend/app/ectd/scaffold.py) — the regional files come from the region's `REGIONAL_BACKBONES` entry (Phase 4b) |
| **VNeeS** | **Not started** | zero occurrences in the codebase |
| **HTML output** | **Not started** | zero occurrences |
| FDA regional backbone (`m1/us/us-regional.xml`) | **Works (Phase 4b)** — original application + amendments | [us_regional.py](backend/app/ectd/us_regional.py) — validates against FDA's `us-regional-v3-3.dtd`; every code it can write is tested against FDA's published code lists |
| eCTD v4.0 / HL7 RPS | **Not started** | interface seam only (`BackboneBuilder` ABC) |

### 4.2 Is the XML backbone real?

Yes. It is not a template string — it is built with lxml using real namespaces, carries `dtd-version="3.2"`, a `<!DOCTYPE>` pointing at the shipped DTD, per-leaf `checksum`/`checksum-type="md5"`/`xlink:href`, and **self-validates against the ICH DTD before returning** ([index_xml.py:750](backend/app/ectd/index_xml.py#L750)). The DTD's own misspelled xlink namespace (`w3c.org`) is reproduced verbatim because DTD `#FIXED` matching is exact ([leaf.py:41](backend/app/ectd/leaf.py#L41)).

Lifecycle operations are DTD-compliant: `new | replace | append | delete`, and `build_leaf_element` **refuses** a non-`new` operation that names no earlier leaf ([leaf.py](backend/app/ectd/leaf.py)). ~~`modified-file` pointing at `../<prior-seq>/<path>#<prior-leaf-id>`~~ **Corrected in Phase 4a:** `modified-file` now points at the earlier sequence's *backbone file* plus the leaf ID (`../0000/index.xml#ID-…`, or `../../../0000/m1/eu/eu-regional.xml#ID-…` from the regional file), as ICH v3.2.2 Appendix 6 specifies, and names the sequence that actually holds that leaf rather than the immediately prior one. Unchanged leaves are correctly **omitted** from the sequence's own backbone while being carried forward in a persisted cumulative view ([lifecycle.py](backend/app/ectd/lifecycle.py)).

Caveats, all self-documented:
- `delete` is implemented but **not covered by an end-to-end build** — only by unit tests. **Phase 4a** made it spec-conformant (no `xlink:href`, empty checksum, per ICH) and proved the validator accepts it (`test_a_delete_leaf_carries_no_file_and_is_not_a_dangling_reference`); before that, every delete restated a path inside the new sequence where no file exists, which our own M05 would have failed.
- `append` is in the vocabulary but is **never produced** by `resolve_lifecycle` — it only ever emits `new`, `replace`, `delete`.
- The EU envelope's agency / procedure-type / country values are **hard-coded constants**, because `Project` does not model them ([regional.py:20](backend/app/ectd/regional.py#L20)).

### 4.3 Regulator-specific profile abstraction — real, but only two profiles and only half the stack

`RegionProfile` ([region_profiles.py:252](backend/app/ctd/region_profiles.py#L252)) holds Module 1 slots, uploaded-document slots, required certificate/declaration types, 3.2.R contents, the BE acceptance window, the test-batch rule, and the applicability table. `NAFDAC_PROFILE`, `EU_PROFILE` and (**Phase 4b**) `FDA_PROFILE` are registered; `get_region_profile` raises on anything else. The builders never branch on region — they walk the profile.

**But:** the abstraction covers *content selection*, not *output format*. The moment you reach the backbone, region is a hard `if`:

```python
if project.region != Region.EU:
    raise NotImplementedError(...)   # backbone.py:64
```

So NAFDAC logic is **not** hard-coded into the core — but eCTD publishing is EU-hard-coded, and NAFDAC is structurally unable to reach it. NAFDAC's path is the folder-tree CTD builder, which is correct for NAPAMS (no backbone required) but means the two regions exercise two different publishing pipelines.

**Replaced in Phase 4b.** The `if` is gone. `V322BackboneBuilder` looks the region up in `REGIONAL_BACKBONES` ([backbone.py](backend/app/ectd/backbone.py)) — one row per region holding the regional file's path, its util files, its builder and an optional pre-flight check. `BackboneBuilder` stays the *spec-version* seam (P12's v4.0) and the table is the *region* seam, because the two vary independently. A region with no row raises `EctdNotSupportedError` with a reason: NAFDAC's says it takes CTD, and names the endpoint that builds it.

---

## 5. VALIDATION ENGINE

Three layers, one `Finding` type, merged into one `Report` by `Finding.source` ([report.py](backend/app/ectd/report.py)).

### 5.1 Layer 1 — data rules (33), `source="data-rule"`

Registered by decorator in [rules.py](backend/app/validation/rules.py); engine at [engine.py:run_all](backend/app/validation/engine.py#L92). Severity: `ERROR` blocks export, `WARNING`/`INFO` do not, `ADVISORY` is structurally incapable of blocking.

| ID | Severity | What it checks | Audit category |
|---|---|---|---|
| R01 | ERROR | Strength stated in narrative ≠ that active's declared strength | regional business rule (cross-module consistency) |
| R02 | ERROR | Narrative names a dosage form other than the product's | regional business rule |
| R03 | ERROR | Another product's brand name appears (copy-paste contamination) | regional business rule |
| R04 | WARNING | Batch-formula quantity vs strength × salt factor × batch size | regional business rule (arithmetic) |
| R05 | ERROR | Claimed shelf life ≤ longest passing long-term timepoint | regional business rule |
| R06 | ERROR/WARN | Multisource filing takes exactly one BE route (study or biowaiver) | regional business rule |
| R07 | ERROR | Every active has a specification with test rows (3.2.S.4.1) | structural/completeness |
| R08 | ERROR | Every manufacturer's GMP status is CERTIFIED | regional business rule |
| R09 | ERROR | An API's linked manufacturer plays the API_MANUFACTURER role | lifecycle/referential integrity |
| R10 | WARNING | Residual solvent above ICH Q3C class limit (heuristic text parse) | regional business rule |
| R11 | INFO | Compendial citation should be re-checked against current edition | regional business rule |
| R12 | WARNING | Declared pack size appears in an artwork/label packaging row | regional business rule |
| R13 | ERROR | Region-required certificates present **and unexpired** (NAFDAC: CPP) | regional business rule |
| R14 | ERROR | **NAFDAC-only** — filing names its applicant | regional business rule |
| R15 | ERROR/WARN | Attached declarations are signed (+ notarized where required) | structural/completeness |
| R16 | ERROR | Region-required declarations are present at all | regional business rule |
| R17 | ERROR | Every active names its manufacturer (DTD `#REQUIRED`) | XML/schema precondition |
| R18 | ERROR | A section declared not-applicable carries no content | lifecycle/referential integrity |
| R19 | WARNING | Every conditional section has a yes/no answer | structural/completeness |
| R20 | ERROR | No applicable leaf ships as a placeholder | structural/file |
| R21 | ERROR | Animal/human-origin excipient has TSE/BSE evidence | regional business rule |
| R22 | ERROR/INFO | Batch analysis result within its own acceptance criterion | regional business rule |
| R23 | ERROR/INFO | Stability result within shelf life meets its criterion | regional business rule |
| R24 | WARNING | Shelf life not resting on accelerated data alone | regional business rule |
| R25 | ERROR | 90 % CI inside the region's acceptance window (NTI-aware) | regional business rule |
| R26 | ERROR/WARN | Study comparator = the reference product the application declares | lifecycle/referential integrity |
| R27 | ERROR | BE test batch ≥ the region's fraction of commercial scale | regional business rule |
| R28 | ERROR | Leaflet/SmPC 6.1 excipients ↔ batch formula, both directions | regional business rule |
| R29 | ERROR | Label storage temperature supported by an actual study condition | regional business rule |
| R30 | ERROR/WARN | SmPC's authored sections are authored | structural/completeness |
| R31 | ERROR | SmPC/label/leaflet agree on strength, shelf life, storage, pack size — **a declared tripwire** (Phase 5b): cannot fire on today's data by design | regional business rule |
| R32 | WARNING | Every SmPC contraindication recognisable in the leaflet | regional business rule |
| R33 | WARNING | Approved leaflet text meets the plain-language register | regional business rule |

Only **R14** is region-scoped (`regions=[Region.NAFDAC]`); the other 32 run for every region. **Phase 4b** adds **R34** (FDA admin data: D-U-N-S, contact, six-digit application number, application type — ERROR) and **R35** (FDA publishes original applications only — ERROR for a renewal or variation), both `regions=[Region.FDA]`. R31 is documented by its own author as *currently unable to fire* because all three documents render from one `shared_values` call — it is a regression guard, not an active check. **Phase 5b:** that status is now declared in the registry (`@rule("R31", tripwire=True)`), a test holds every tripwire silent on every seed in every region, and R31's own forcing test proves it still fires on the regression it guards. Kept running rather than disabled: disabling would remove the only guard against that regression, and teaching it to read prose would duplicate R01.

### 5.2 Layer 2 — mechanical eCTD checks (~~12~~ ~~13~~ 16), `source="mechanical-ectd"`

Re-validate the **built ZIP**, not the data ([validate.py](backend/app/ectd/validate.py)). Pure functions over `{path: bytes}`.

| ID | Severity | Check | Category |
|---|---|---|---|
| M01 | ERROR | `index.xml` validates against `ich-ectd-3-2.dtd` | XML/schema |
| M02 | ERROR | The regional backbone validates against its region's DTD — ~~`eu-regional.xml` only~~ EU and FDA since **Phase 4c** (found by path, not told the region) | XML/schema |
| M03 | ERROR | Each leaf's stated checksum = the file's actual MD5 | structural/file |
| M04 | ERROR | `index-md5.txt` matches `index.xml`'s actual MD5 | structural/file |
| M05 | ERROR | Every leaf `xlink:href` resolves to a file in the package | structural/file |
| M06 | WARNING | No orphan files (in the package, referenced by no leaf). **Phase 4a:** the regional backbone is no longer exempt — index.xml now references it | structural/file |
| M07 | ERROR | Non-`new` leaf has a `modified-file` naming an earlier sequence's backbone file + a leaf ID (ICH form; **Phase 4a**) | lifecycle/referential integrity |
| M08 | ERROR | The prior sequence a `modified-file` targets was actually built | lifecycle/referential integrity |
| M09 | ERROR | That leaf ID really exists in the **same** backbone file of that sequence (**Phase 4a**: was "ID + document path") | lifecycle/referential integrity |
| M10 | ERROR | No PDF is encrypted | structural/file |
| M11 | WARNING | PDF page 1 has extractable text (proxy for "not a scan") | structural/file |
| M12 | ERROR | Every expanded section instance has appeared live in some sequence | structural/completeness |
| M13 | ERROR | **Phase 4c.** Every code in `us-regional.xml` is "active" in FDA's published code lists — the check FDA's DTD cannot make, since it types those attributes as CDATA | FDA code conformance |
| M14 | ERROR | **Phase 5a.** Every folder and file name is an ICH name: `a-z`, `0-9`, `-` only, one extension (ICH v3.2.2 Appendix 2) | naming |
| M15 | ERROR | **Phase 5a.** No folder or file name exceeds 64 characters | naming |
| M16 | ERROR | **Phase 5a.** No path exceeds the region's limit, counted from the sequence folder: FDA 150, EU 180, ICH's own 230 otherwise | naming |

**Documented gap, not a silent skip:** font embedding is not checked ([validate.py:249](backend/app/ectd/validate.py#L249)). ~~There are also **no filename-convention checks** — no path-length limit, no character-set restriction, no folder-naming validation. That entire category is absent.~~ **Closed in Phase 5a** (M14–M16).

### 5.3 Layer 3 — external validator + AI reviewer

- `EXT00` (ADVISORY): the only external-validator output. [`NullExternalValidator`](backend/app/ectd/external_validator.py#L38) is the **sole implementation**; it emits a finding saying no agency-recognized validator ran. The seam is real, the validator is not.
- AI reviewer ([ai_review.py](backend/app/ectd/ai_review.py)): LLM advisory findings, `ADVISORY` only by construction, citations parsed against a strict regex and dropped if unmatched. A provider failure degrades to a visible `AI99` ADVISORY finding rather than failing the report ([report.py:110](backend/app/ectd/report.py#L110)).

### 5.4 Report format and determinism

**Format:** a JSON list of `FindingRead{rule_id, severity, category, message, section, source}` plus `is_exportable` and `overridden_rule_ids` ([schemas/validation.py](backend/app/schemas/validation.py)). Served by `GET /projects/{id}/readiness` (data rules) and `POST /projects/{id}/validate/ectd` (all four layers merged). ~~There is **no human-readable report artifact** — no PDF, no HTML, no CSV export of findings.~~ **Phase 5b:** `GET /projects/{id}/validation-report` renders the same findings as a PDF through the existing DOCX→PDF pipeline — readiness by default, one sequence's full eCTD validation with `?sequence_id=` — with waived checks and their recorded reasons in their own section. A download button sits on the Validation tab.

**Determinism:** the data-rule and mechanical layers are deterministic — `run_all` iterates a fixed registry in registration order, rules are pure functions over the loaded aggregate, and pass/fail per rule is explicit. Two real caveats:
- The **AI reviewer layer is not deterministic** by nature. It is quarantined to `ADVISORY` and cannot affect `is_exportable`, so *the gate* is deterministic even though *the report* is not.
- R10's residual-solvent check parses free text heuristically and is flagged WARNING precisely because of that.

---

## 6. SUBMISSION LIFECYCLE MANAGEMENT

### 6.1 Sequence tracking — yes

`Sequence` rows auto-number `0000`, `0001`, … server-side via `max()` ([projects.py:147](backend/app/api/routers/projects.py#L147)); the number is never client-supplied. **Phase 4b:** the first number is the region's (`RegionProfile.first_sequence_number`) — FDA's conformance guide says to "begin with sequence number 0001". **Updated (Phase 1):** that `max()`-then-insert was a race — two concurrent POSTs could both take the same number — and is now backed by a `UniqueConstraint("project_id", "number")` plus a bounded retry. Verified by reproducing the collision against real Postgres with the constraint removed. Each build persists a complete `SequenceLeaf` inventory (section_key, leaf_id, title, path, checksum, operation, modified_file), idempotently — a rebuild deletes and rewrites the rows.

### 6.2 Diffing between sequences — yes, by checksum, and it is the best-engineered part of the repo

[`resolve_lifecycle`](backend/app/ectd/lifecycle.py#L63) diffs the new build against the prior sequence's **cumulative** state on `section_key`, and returns two deliberately separate views: `backbone_leaves` (what this sequence's `index.xml` restates — unchanged leaves omitted, per real eCTD semantics) and `cumulative_leaves` (full current state, persisted so the *next* sequence has something complete to diff against). Added → `new`; checksum changed → `replace` with a `modified-file` back-reference; absent from the new build → `delete`.

**Limits:**
- The diff is exposed only as the `operations` dict returned by a build (`{section_key: "new"|"replace"|"delete"}`). There is **no diff endpoint** — you cannot ask "what changed between 0001 and 0002" without rebuilding.
- `append` is never generated.
- Diff granularity is whole-document checksum. No content-level diff, no redline.

### 6.3 Submission status — ~~essentially absent~~ **present (Phase 3)**

~~`Sequence` has exactly three non-key columns... There is **no status enum**, no submission type per sequence.~~ **Closed in Phase 3.** `Sequence` now carries `status` (`SequenceStatus`: draft → built → submitted → acknowledged → under-review → approved/rejected) and `submission_unit_type`.

Status moves only through `PATCH /projects/{id}/sequences/{seq_id}/status`, which enforces `ALLOWED_SEQUENCE_TRANSITIONS` and answers **409** on an illegal jump, naming what *was* possible. Deliberately *not* settable by the ordinary PATCH: a status any PATCH can set is a status that can record a history which never happened (DRAFT straight to APPROVED, or a rejection quietly reopened). Transitioning to SUBMITTED stamps `submitted_at` if absent — a sequence marked submitted with no date cannot answer the question it exists to answer.

**Still absent:** gateway/ESG transmission records and acknowledgement receipts. `ACKNOWLEDGED` is currently a human assertion, not a parsed gateway response.

### 6.4 Regulator correspondence — ~~not started~~ **present (Phase 3)**

~~No entity, endpoint, or field anywhere.~~ **Closed in Phase 3.** A `correspondence` table with direction (inbound/outbound), type (deficiency letter / query / response / commitment / other), subject, `received_or_sent_at`, a nullable `due_date`, open/closed status, optional notes, and optional links to both a sequence and an uploaded document. CRUD under `/projects/{id}/correspondence`, mounted through the same `build_child_router` factory `Declaration` uses.

The `due_date` is the point: missing a deficiency-letter deadline can lapse an application — the dossier is fine and the registration is lost on a date. `is_overdue` is derived at read time, never stored, because "is this late?" is a question about today. A closed item is never overdue however old its due date.

---

## 7. CLI / API SURFACE

### 7.1 CLI — 6 scripts, no dossier-building CLI

| Command | What it does today | Verified |
|---|---|---|
| `uv run python -m scripts.check_target_toc [--strict] [--project <id>]` | Compares `docs/target-toc.yaml` (98 leaves) against what the platform can produce; `--strict` exits non-zero on a gap; `--project` asks the same of one filing's real data | **Run in this audit.** Output: `COVERAGE: 98/98 leaves`, 22 upload-dependent; exit 0 |
| `uv run python run_demo.py` | Seeds buggy + corrected LAMOX on in-memory SQLite, runs the rule engine, prints both reports, renders 3.2.P.1 | Not run (competes with test suite); code path is the same one `tests/test_seed_demo.py` covers |
| `uv run python -m scripts.seed_demo` | Seeds a demo project into the configured database | Not run (needs a live DB) |
| `uv run python -m scripts.seed_kb` | Ingests `reference/kb_sources/ich/*.pdf` into the pgvector KB | Not run (needs Postgres + pgvector) |
| `uv run python -m scripts.promote_admin` | Promotes a user to ADMIN role | Not run |
| `uv run python -m scripts.make_section_templates` | Generates the 38 `.docx` section templates (1821 LOC) | Not run |

### 7.2 API — 160 operations, enumerated from the live OpenAPI schema

Obtained by `app.openapi()`, not by reading route decorators.

**Auth & admin (5):** `POST /auth/register`, `POST /auth/login` (JWT + argon2), `GET /auth/me`, `GET /admin/users`, `PATCH /admin/users/{id}`.

**Master data (12):** `/applicants` and `/products` full CRUD; `GET /enums` (every enum for the UI); `GET /regions` (region profiles); `GET /sections` (the 72 registered sections with their narrative slots).

**Product children — generated CRUD (~90):** one 5-verb router per collection, built by a factory in [product_children.py](backend/app/api/routers/product_children.py): `apis`, `manufacturers`, `excipients`, `packaging`, `batch-formula`, `batches`, `impurities`, `specification`, `stability`, `clinical`, `bioequivalence`, `biowaivers`, `reference-products`, `certificates`; plus drug-substance children `/apis/{id}/specification`, `/apis/{id}/batches`, `/apis/{id}/impurities`, `/apis/{id}/stability`, and `/excipients/{id}/specification`, `/projects/{id}/declarations`.

**Result grids (12):** `/batches/{id}/results`, `/stability/{id}/results` (incl. bulk `PUT`), `/bioequivalence/{id}/results` (bulk `PUT`).

**Project & dossier (14):**
- `POST|GET|PATCH|DELETE /projects…`
- `POST|GET|PATCH /projects/{id}/sequences…` — auto-numbered
- `GET /projects/{id}/section-status` — every owed leaf + status
- `PATCH /projects/{id}/conditions` — answer conditional-section questions
- `GET|PUT|DELETE /projects/{id}/documents/{section_number}` — upload/replace/remove a leaf's file
- `GET /projects/{id}/artifacts?key=…` — download a built ZIP (prefix-checked against the project)

**Build & validate (6):**
- `POST /projects/{id}/build/ctd` — folder-tree CTD ZIP
- `POST /projects/{id}/build/ectd` — eCTD sequence ZIP (**422 for non-EU**)
- `POST /projects/{id}/validate/ectd` — merged 4-layer report on a built sequence
- `GET /projects/{id}/readiness` — data-rule report + export gate
- `POST /projects/{id}/validation-overrides`, `…:withdraw`, `GET …/validation-overrides`

**Product information (3):** `GET|PUT /products/{id}/product-information`, `GET /projects/{id}/product-information/comparison`.

**Narrative / LLM (4):** `POST …/narrative/{slot}:generate`, `GET …/narrative/{slot}`, `POST …:approve`, `POST …:edit`.

**Knowledge base (2):** `POST /kb/ingest` (admin-gated), `GET /kb/search`.

**Health (1):** `GET /health`.

Ownership is enforced by a `require_project_owner` / owner-scoped dependency on the routers, tested in `tests/test_ownership.py` (20 tests).

---

## 8. TEST COVERAGE & RELIABILITY

### 8.1 Automated

- **Backend:** 494 test functions across 48 test modules in [backend/tests/](backend/tests/). **Executed in this audit: `30 failed, 519 passed, 12 skipped in 4274.70s (1:11:14)`.** The suite takes **over an hour** on this machine — see 8.3 #9.
  - **27 of the 30 are environmental**, all one root cause: `botocore EndpointConnectionError` against `localhost:9000` because the committed `.env` sets `STORAGE_PROVIDER=s3` and MinIO is not running (8.3 #2). Verified, not assumed: re-running `test_validation_api`, `test_module1_api`, `test_documents` and `test_artifacts_api` under `STORAGE_PROVIDER=memory` gave **43 passed, 1 failed**.
  - **3 are genuine stale-test failures that persist under `STORAGE_PROVIDER=memory`** — see 8.3 #1. **CI is therefore red at this baseline**, since CI runs `uv run pytest -q`.
- **Frontend:** **73 tests in 8 files, all passing** — verified by running `npx vitest run` in this audit (23.5 s). Covers `lib/acceptance`, `lib/api`, `lib/wizard-steps`, `lib/paste-table`, `lib/narrative-status`, `AuthGuard`, `ui`, wizard navigation.
- **Target-TOC gate:** `check_target_toc --strict` — verified passing, exit 0, 98/98.
- **CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml)): ruff → black --check → pytest → target-TOC gate, on Postgres+pgvector, with LibreOffice installed and `EMBEDDING_PROVIDER=fake` / `LLM_PROVIDER=fake`.

Notably well-covered: eCTD build and lifecycle (16 tests), mechanical eCTD checks (15 tests, each defect injected deliberately), validation rules (21), product information (42), bioequivalence (27), repeat axes (25), control sections (25), ownership (20), and an end-to-end worked example (5 tests) that builds the full amlodipine dossier and DTD-validates its backbone.

### 8.2 Only manually exercised / not in CI

- **Playwright e2e** — one spec, [frontend/e2e/happy-path.spec.ts](frontend/e2e/happy-path.spec.ts). Not run in CI (the CI workflow has no frontend job at all).
- **Frontend unit tests** — pass locally, **not run by CI** at this baseline. Nothing stops a frontend regression from merging. *(A frontend CI job is present in the uncommitted P25 work.)*
- **docker-compose stack** (Postgres + MinIO + API) — README documents it; not exercised by any automated test.
- **`scripts/seed_demo.py`, `scripts/seed_kb.py`, `scripts/promote_admin.py`, `scripts/make_section_templates.py`** — no tests import them.
- **S3/MinIO storage backend** — tests use `InMemoryStorageClient`; `S3StorageClient` has no test coverage.
- **Real LLM / embedding providers** — CI uses `fake`. The Gemini/Voyage paths are untested against the real services.

### 8.3 Known broken, fragile, or explicitly untested paths

1. **Three tests fail at HEAD for non-environmental reasons — CI is red.** All three are stale tests that a later phase invalidated and nobody updated:
   - `tests/test_ctd_build.py::test_package_places_every_document_in_its_correct_folder` and `::test_a_combination_product_builds_end_to_end` — `EXPECTED_PATHS` at [test_ctd_build.py:34](backend/tests/test_ctd_build.py#L34) still expects `m1/12-administrative-information/1.2.pdf`. P24d (`ec1c8be`) renumbered that leaf because 1.2 is a *heading*, not a document; the registry now has `1.2.1`/`1.2.2` and no `1.2` (confirmed: `'1.2' in SECTIONS` → `False`). The test constant was not updated with the section.
   - `tests/test_module1_api.py::test_a_nafdac_dossier_reaches_exportable_through_the_api_alone` — asserts `blocking == []`, but rule **R30** (product-information completeness, added in P23) returns an ERROR because the test never enters product information. The test predates the rule.
   All three confirmed under `STORAGE_PROVIDER=memory`, so none is the MinIO issue below.

2. **27 further test failures come from ambient environment, not from a fixture.** Tests that call `get_storage_client()` resolve storage from settings. The repo default is `memory` ([config.py:26](backend/app/core/config.py#L26)) but the **committed `.env` sets `STORAGE_PROVIDER=s3`**, so they fail with `EndpointConnectionError` against `localhost:9000` whenever MinIO is not running. Verified: the same files give 43 passed / 1 failed under `STORAGE_PROVIDER=memory`. CI never sets the variable, so it takes the `memory` default and has never seen this. Most of the suite injects an `InMemoryStorageClient` explicitly; these do not. Affects `test_artifacts_api`, `test_ctd_api`, `test_documents`, `test_ectd_api`, `test_module1_api`, `test_validation_api`.

3. **eCTD build is impossible for NAFDAC.** *(Phase 4b: correct by design — ADR 0001 — and the 422 now says so instead of "not built yet".)* `build_ectd_sequence` → `V322BackboneBuilder.build` raises `NotImplementedError` unless `project.region == Region.EU`; the router converts it to a 422 ([ectd.py:87](backend/app/api/routers/ectd.py#L87)). Both eCTD tests set `project.region = Region.EU` first. Given `Region.NAFDAC` is the default, **the default configuration cannot produce an eCTD sequence.**

4. **`delete` lifecycle operation is not golden-fixture tested** — stated in-code at [lifecycle.py:129](backend/app/ectd/lifecycle.py#L129).

5. **`append` is never emitted** by the resolver despite being in the DTD vocabulary and the column.

6. **Sequence numbering has a race.** No unique constraint on `(project_id, number)`; `create_sequence` reads `max()` then inserts. *(Being fixed in the uncommitted P25 work — see the baseline caveat at the top.)*

7. **R31 cannot currently fire** — its own docstring says so. It is a guard against a future regression, not an active check. *(Phase 5b: declared as a tripwire in the registry, and tested as one.)*

8. **Font embedding unchecked** in PDFs ([validate.py:249](backend/app/ectd/validate.py#L249)).

9. **Hard dependency on LibreOffice.** Every document goes through `soffice --headless`; a missing binary raises `PdfConversionError`. This is also why the suite takes **1:11:14** — `tests/test_ctd_build.py` + `test_ctd_api.py` + `test_ectd_api.py` alone took 37 minutes — even with the `lru_cache(256)` on conversions.

10. **Destructive-migration incident on record.** [reference/build-log.md](reference/build-log.md) documents a migration test that once ran a real downgrade against the dev Postgres and dropped every table. Mitigated (the test now monkeypatches `DATABASE_URL` and asserts the target), but the class of risk is documented.

11. **README is stale.** Its Roadmap still lists "eCTD v3.2.2 XML backbone generation" and "wire validation behind a `/readiness` API endpoint" as future work; both are built. *(Being fixed in the uncommitted P25 work.)*

---

## 9. GAP LIST

Measured against LORENZ docuBridge / Extedo EXTEDOPHARMA capability sets.

### 9.1 Regulatory data model
- No Organization/Company/Tenant entity — authorization is one `owner_id` per user. No teams, no roles beyond USER/ADMIN, no delegation.
- No Application entity and **no agency application/dossier number field anywhere**.
- No Submission entity distinct from Sequence; no submission type per sequence (initial / variation / renewal / response).
- No Document or DocumentVersion entity — see 9.2.
- No lifecycle operation as stored, constrained data (a `String(10)`, no enum, no CHECK).
- No product-family / multi-strength modelling: a `Project` is one `Product`, and a `Product` has one dosage form. **A single filing cannot span two strengths.**
- No controlled vocabulary / metadata dictionary service; enums are Python.
- No audit log table. Only `ValidationOverride` and `NarrativeGeneration` are auditable.

### 9.2 Document management
- **No version history at all.** Re-upload overwrites bytes and row.
- No check-in/check-out, no locking, no concurrent-edit protection.
- No document status, owner, effective/expiry date, author, language, or granularity metadata.
- No approval workflow, no reviewer assignment, no e-signature, no 21 CFR Part 11 compliance.
- No document reuse across filings — a `SectionDocument` is scoped to one project; the same CPP must be re-uploaded per project.
- No PDF remediation toolchain: no bookmark-tree generation, no hyperlink/cross-reference creation, no OCR, no PDF/A conversion, no font embedding, no page-count/size validation, no PDF sanitisation.
- No full-text search over documents (the pgvector KB indexes *guidelines*, not dossier documents).
- No Word round-trip authoring, no template-driven co-authoring, no MS Office integration.

### 9.3 Dossier / CTD workspace
- No visual drag-and-drop dossier tree; the UI is a section list.
- CTD structure is **hard-coded in three Python files**; adding a section is a code change, not configuration.
- Only two submission types (`MULTISOURCE_GENERIC`, `NEW_CHEMICAL_ENTITY`) and ~~two~~ three regions (NAFDAC, EU, FDA since Phase 4b).
- No reuse/copy of a dossier or a module between projects; no baseline/cloning.
- No placeholder-vs-content status view per node beyond the section-status list.
- No concurrent multi-user workspace, no per-section assignment or progress tracking.

### 9.4 Publishing engine
- ~~**No FDA (`us-regional.xml`) backbone.**~~ **FDA built in Phase 4b** (original application + amendments; no supplements, no upload slot for FDA's own forms). No Health Canada, no Swissmedic, no ASEAN, no GCC, no Japan.
- **No VNeeS** (EU veterinary), no NeeS, no HTML rendering.
- **No eCTD v4.0 / HL7 RPS** — only an ABC seam.
- **NAFDAC cannot produce an eCTD sequence at all** (raises) — by design, per ADR 0001; since Phase 4b the refusal says so.
- EU envelope values (agency, procedure type, country) hard-coded; not modelled per project.
- No STF (Study Tagging File) support for Modules 4/5.
- No cross-document hyperlink or bookmark-tree publishing — one flat bookmark per leaf.
- No submission-ready media output (gateway package, ESG/AS2 transmission, eSubmission Gateway).
- No incremental/partial republish; a build regenerates everything.
- No publishing job queue, progress reporting, or cancellation — builds are synchronous HTTP requests that shell out to LibreOffice per document.

### 9.5 Validation engine
- ~~**No filename/path convention checks whatsoever**~~ **Closed in Phase 5a:** M14–M16 check ICH characters, 64-character names and the region's path limit — and the builder's own names were fixed first, because two thirds of every package broke the rule.
- No agency validation-criteria packs (FDA/EMA published criteria, versioned, selectable per region) — 33 hand-written rules instead.
- **No real external validator.** `NullExternalValidator` is the only implementation; it exists to say nothing ran.
- No PDF technical validation: version, PDF/A, font embedding, security settings beyond encryption, page size, image resolution, bookmark presence.
- No XML well-formedness checks beyond the two DTDs; no schema validation for v4.0.
- No validation profiles / severity configuration per region; no rule enable/disable.
- ~~No validation report artifact — no PDF/HTML/Excel export, no shareable report file. JSON over HTTP only.~~ **Closed in Phase 5b** (PDF report endpoint + download button).
- Cumulative validation is partial: M12 checks completeness against this sequence's cumulative `SequenceLeaf` view, and prior packages are fetched only to resolve `modified-file` targets. There is no "validate the whole application across every sequence" report.
- R31 is inert by construction — now a declared, tested tripwire (Phase 5b); R10 is heuristic.

### 9.6 Submission lifecycle management
- **No submission status model** — three columns on `Sequence`, one of them a nullable timestamp.
- **No regulator correspondence tracking at all** — no questions, deficiency letters, responses, commitments, or deadlines.
- No gateway submission or acknowledgement (ACK1/2/3) tracking.
- No lifecycle/current-view reconstruction UI — the cumulative state exists in `sequence_leaf` but nothing renders "what is the dossier today across all sequences".
- No diff endpoint or diff report between two arbitrary sequences.
- No `append` operation; `delete` untested by fixtures.
- No variation/renewal workflow, no commitment tracking, no submission calendar.
- No archive, no long-term retention policy, no export of a complete application.

---

## 10. HONEST MATURITY RATING

Scale: **Not started** / **Prototype** (works on a happy path, gaps that block real use) / **Functional** (does the job end-to-end for its declared scope, with known limits) / **Production-grade** (a regulated company could file with it as-is).

### 1. Regulatory data model — **Functional**
32 mapped tables across 27 model files, 22 migrations, real FKs with declared cascades, a CHECK-constrained polymorphic owner ([spec_owner.py](backend/app/models/spec_owner.py)), and a genuinely non-trivial domain decomposition — strength lives on `ActiveIngredient` so combination products are representable ([product.py:26](backend/app/models/product.py#L26)), specification tests are shared across three owners so the same limit is never copied. It is *Functional* and not *Production-grade* because the entities a commercial platform is organised around — Organization, Application, Document, DocumentVersion — are simply absent, and a filing cannot span two strengths.

### 2. Document management — **Prototype**
Upload works, is magic-byte checked, converts DOCX at ingest so the MD5 is settled once, and is keyed to a CTD instance with a real unique constraint ([section_document.py:39](backend/app/models/section_document.py#L39)). But there is no version history (the model file says so at line 28), no status, no approval workflow, no locking, and no reuse across projects. The only state machine in the system, `NarrativeStatus` ([enums.py:378](backend/app/models/enums.py#L378)), governs LLM prose — not documents.

### 3. Dossier / CTD workspace — **Functional**
`scripts/check_target_toc --strict` was **executed during this audit** and reported `COVERAGE: 98/98 leaves`, exit 0, against a contract ([docs/target-toc.yaml](docs/target-toc.yaml)) derived leaf-by-leaf from a real filed dossier. `GET /projects/{id}/section-status` + `PATCH /conditions` give a working applicability workspace with conditional questions and generated not-applicable statements. Held below *Production-grade* by the structure being hard-coded across [registry.py](backend/app/templating/registry.py#L127), [structure.py](backend/app/ctd/structure.py#L24) and [index_xml.py](backend/app/ectd/index_xml.py#L481), and by two submission types / two regions.

### 4. Publishing engine — **Functional (EU eCTD) / Functional (NAFDAC CTD) / Not started (everything else)**
The EU eCTD path is real: [`build_index_xml`](backend/app/ectd/index_xml.py#L700) DTD-validates before returning, [`build_leaf_element`](backend/app/ectd/leaf.py#L74) refuses a non-`new` operation without `modified-file`, and `test_the_worked_example_produces_a_dtd_valid_ectd_backbone` builds the full amlodipine dossier and validates it against the shipped ICH DTD. Determinism is engineered, not assumed — pinned zip timestamps, pinned PDF `/CreationDate`, content-derived `/ID` ([pdf.py:128](backend/app/assembly/pdf.py#L128)).
The rating stops at *Functional* because of a hard ceiling: [backbone.py:64](backend/app/ectd/backbone.py#L64) raises for every region except EU, so the platform's own default region **cannot publish eCTD at all**. No FDA, no VNeeS, no HTML, no v4.0. *(Phase 4b: FDA added; NAFDAC's refusal is now by design, per ADR 0001.)*

### 5. Validation engine — **Functional**
45 checks actually run (33 data rules + 12 mechanical), each returning a message that names the offending values, with a four-level severity model whose `ADVISORY` tier is structurally incapable of gating an export ([engine.py:44](backend/app/validation/engine.py#L44)). The export gate is enforced in exactly one place — `AssemblyBlockedError` in [assemble.py](backend/app/assembly/assemble.py#L36) — which both builders inherit. Overrides are attributed, reasoned (≥20 chars), and withdrawable without destroying the original decision.
Not *Production-grade*: the entire filename-convention category is missing, there is no agency criteria pack, no report artifact, and `NullExternalValidator` ([external_validator.py:38](backend/app/ectd/external_validator.py#L38)) means nothing agency-recognized has ever validated this output.

### 6. Submission lifecycle management — **Prototype**
[`resolve_lifecycle`](backend/app/ectd/lifecycle.py#L63) is genuinely well-built — it gets the hard part right (unchanged leaves omitted from the backbone but carried in a persisted cumulative view), and M07–M09 re-verify every `modified-file` against the prior sequence's actual package. But the surrounding lifecycle *management* barely exists: `Sequence` has three columns ([sequence.py:26](backend/app/models/sequence.py#L26)), there is no status enum, no diff endpoint, no current-view reconstruction, `append` is never emitted, and regulator correspondence has no representation anywhere in the schema.

---

## Summary

| Area | Rating |
|---|---|
| 1. Regulatory data model | **Functional** |
| 2. Document management | **Prototype** |
| 3. Dossier / CTD workspace | **Functional** |
| 4. Publishing engine | **Functional (EU + FDA eCTD, NAFDAC CTD)** |
| 5. Validation engine | **Functional** |
| 6. Submission lifecycle management | **Prototype** |

The engineering discipline here is unusually high for a project this size — determinism is tested rather than assumed, regulatory parameters live in config with the reasoning recorded, and rejected design alternatives are documented in the code. What separates it from a LORENZ/Extedo-class platform is not code quality but **surface area**: one region can publish eCTD, documents have no versions or workflow, there is no correspondence tracking, no filename validation, and no agency-recognized validator has ever seen the output.

---

## Change log against this audit

Kept per gap.md phase, under the audit's own six headings so the document
stays diffable against the LORENZ/Extedo comparison.

### Phase 0 — NAFDAC technical format (decision only, no code)

Not a change to any of the six areas; it settles what **4. Publishing
engine** should build next. NAFDAC's in-force guideline (DR&R-GDL-005-03,
effective 20/03/2025) requires CTD uploaded to NAPAMS/DMS and never mentions
eCTD, XML, backbone, checksum, MD5 or sequence across 12 pages. NAFDAC
therefore stays CTD-only and the folder-tree builder is already correct for
it; the second backbone targets **FDA** instead. Recorded in
[docs/decisions/0001-nafdac-format.md](docs/decisions/0001-nafdac-format.md),
which also records a blocker the audit did not surface: the **US regional
DTD is absent** from `reference/ectd_dtd/`, so the FDA path cannot
self-validate the way the EU path does until it is obtained.

### Phase 1 — operational landmines

**1. Regulatory data model** — one constraint added. `sequence` now carries
`UniqueConstraint("project_id", "number")` (migration
`f5c8b21a90d7`). The migration refuses to run if duplicates already exist
rather than choosing which row keeps a regulatory transaction id.

**6. Submission lifecycle management** — the §6.1 race is closed. The
constraint is the guarantee; a bounded retry in `create_sequence` is the
recovery, returning 503 rather than a number it cannot prove is unique.
Portable on purpose: a Postgres advisory lock would not hold on the SQLite
the suite also runs against. Ratings unchanged — this is a correctness fix,
not new surface area.

**2. Document management / 3. Dossier workspace / 4. Publishing engine /
5. Validation engine** — unchanged.

**Test infrastructure** (not one of the six, but it was making the audit's
own claims unreproducible):

- Object storage is now pinned to the in-memory client by an autouse
  fixture. The two failing `test_artifacts_api.py` tests failed because API
  *routers* call `get_storage_client()` with no injection point, so a
  developer's `STORAGE_PROVIDER=s3` reached them. Reproduced
  (`EndpointConnectionError`) and re-verified fixed. Note the audit's
  premise that `.env` is committed is wrong — it is gitignored
  (`.gitignore:11`), and `.env.example` already matches the code default.
- CI gained a **`frontend` job**: there was none. `npm ci`, eslint, vitest
  (73 tests), `next build`, and the Playwright spec, which skips itself when
  no backend is reachable — so what it actually gates is that the app builds
  and serves, not the full journey.

**Known pre-existing failure, not introduced here:** `black --check` fails
on **7 files untouched by this phase** (stability model/router/templating,
seed demo test, two older migrations). CI's format gate is therefore already
red independent of these changes — most likely drift from the unpinned
`black>=24.0`. Left alone to keep this phase's commit scoped; it needs its
own decision (reformat, or pin black).

### Phase 1a — DOCX→PDF conversion performance

**Not one of the six areas — it is the reason §8.3 #9 said the suite takes
1:11:14.** Re-diagnosed before changing anything, per the phase brief.

**The measurement.** Timing the existing `convert_docx_to_pdf`:

| input | time |
|---|---|
| 1-paragraph `.docx` | 1109 ms |
| 400-paragraph `.docx` | 1134 ms |
| rendered 3.2.P.1 (37 KB) | 1109 ms |

399 extra paragraphs cost **25 ms**. So ~1.1 s of every conversion was
fixed cost — forking `soffice`, building a throwaway profile, registering
filters, bootstrapping UNO — and actual page layout was 10–70 ms. Startup
was **~97%** of every call. §8.3 #9's diagnosis is confirmed.

*A wrong measurement worth recording:* the first probe timed `soffice
--version` and reported startup at 107 ms (8% of a call), which would have
ended the phase. `--version` skips the filter/UNO bootstrap a real
conversion pays for. The honest probe is to convert the smallest possible
document through the real code path.

**The change.** `app/assembly/converter.py` introduces a `DocumentConverter`
protocol with three transports, selected by `DOCUMENT_CONVERTER`:
`libreoffice-listener` (default — one persistent `soffice` driven through
`unoserver`), `soffice-subprocess` (the old behaviour, retained as escape
hatch and fidelity reference), and `gotenberg` (HTTP to a container, added
to `docker-compose.yml` behind a profile). `pdf.py` keeps the contract —
determinism, bookmarks, normalization — and now owns only that.

**Result** (per-document, same machine):

| transport | cold | warm |
|---|---|---|
| `soffice-subprocess` | ~1109 ms | ~1109 ms (every call is cold) |
| `libreoffice-listener` | ~5.9 s (includes starting the listener) | **185–237 ms** |

**6.0x per document, ~924 ms saved on each.** Measured on an idle machine;
a run taken while a concurrent test suite saturated the box (load average
9.7) gave 6438 ms → 1431 ms — absolutes inflated ~5x, ratio held.

**Fidelity is byte-identical**, not merely similar — same MD5
(`55cdceb8…`) from both transports on the 3.2.P.1 fixture. This is
load-bearing, not cosmetic: P09 checksums *are* hashes of these bytes and
`resolve_lifecycle` decides `new` vs `replace` by comparing a leaf's
checksum across sequences, so a one-byte difference would silently mark
every unchanged document as modified in the next sequence. Asserted by
`test_the_listener_produces_byte_identical_output_to_a_fresh_soffice`.

**Operational notes.** Conversions are serialized by a lock (one UNO
listener is not safely reentrant). The listener binds a kernel-chosen free
port, not a fixed one - a fixed port let an orphan from an earlier run
block the next listener, which the restart path turned into a spawn loop
(observed: five listeners alive, suite at ~14 s/test). A dead listener
restarts automatically, once. The listener starts lazily, following this codebase's existing cached-
singleton pattern rather than adding a FastAPI lifespan handler. `python3-uno`
becomes a required system package and CI now installs it and checks it is
importable as an early step. **Known sharp edge:** `python3-uno` is compiled
against the distro's Python, so a minor-version mismatch with the project
interpreter stops the listener starting — documented in
`docs/decisions/0002-document-converter.md`, with `soffice-subprocess` as
the fallback.


### Phase 2 — document versioning

**1. Regulatory data model** — one new table. `document_version`: one
immutable row per upload, with `version_number` unique per
`section_document` (same constraint-plus-retry discipline as the sequence
numbers in Phase 1, because it is the same read-then-insert race). §1.2's
"**DocumentVersion.** Explicitly absent" entry no longer holds.

**2. Document management** — §2.2 flips from Prototype's worst gap to
present. Each version owns its bytes at its own key
(`projects/{id}/documents/versions/{leaf}/v{n}.pdf`); the old deterministic
key was overwriting predecessors, which would have made any history that
pointed at it a lie. Safe to change because `storage_key_for` has exactly
one caller and every consumer reads `document.storage_key` rather than
reconstructing it — verified before changing, not assumed.

**6. Submission lifecycle management** — unchanged by design, and asserted
so: `test_replacing_an_uploaded_document_still_drives_the_lifecycle` builds
a sequence from an uploaded leaf, replaces the document, and proves the next
sequence files it as `replace` with the NEW checksum while version 1's bytes
remain retrievable. If the resolver had read a stale row, a replaced
document would have filed as unchanged and the agency would never have
received the new file.

**3. Dossier workspace / 4. Publishing engine / 5. Validation engine** —
untouched, which was the design goal.

**Bug found and fixed on the way** (not part of the brief): `PUT/GET
/products/{id}/product-information` raised `MissingGreenlet` for any product
with stability results. `_read` attaches derived values → shelf-life
statement → `StabilityStudy.supported_months` → each result →
`meets_criterion` → that result's specification test. The route eager-loaded
`Product.stability` and stopped **two** levels short. It only fires once a
filing has real stability data, which is why no test had reached it; there
is one now.

**Stale tests fixed, making CI green for the first time:** `test_ctd_build`'s
`EXPECTED_PATHS` still expected the pre-P24d `1.2.pdf` (renumbered to
`1.2.2`) and `power-of-attorney-*` filenames (now filed at their leaf
numbers `1.2.4`/`1.2.5`); `test_module1_api` predated rule R30 and never
entered product information — completed through the API rather than by
relaxing the assertion, since "nothing behind the API's back" is the claim
that test exists to make. Backend went from `30 failed, 519 passed` at the
audit baseline to **557 passed, 14 skipped, 0 failed**.

### Phase 3 — sequence status and regulator correspondence

**1. Regulatory data model** — one new table and two new columns.
`correspondence` (project-scoped, nullable sequence), plus
`sequence.status` and `sequence.submission_unit_type`. Both sequence
columns take server defaults, so existing rows become DRAFT/initial with no
backfill — the honest reading in both cases, and for `submission_unit_type`
it preserves exactly what a rebuild produced before.

**4. Publishing engine — a bug fixed, not just a field added.**
`app/ectd/regional.py` hardcoded `submission-unit type="initial"` for every
sequence, so a response to a deficiency letter was filed telling the agency
it was a fresh submission. **DTD-valid, and wrong** — the kind of defect
that survives validation all the way to a reviewer. The value now comes
from the sequence. Asserted by
`test_the_sequence_type_reaches_the_envelope_instead_of_a_hardcoded_initial`.

**6. Submission lifecycle management** — §6.3 and §6.4 above. This is the
area the audit rated *Prototype*; the two findings it named as absent are
now present, though the gateway/acknowledgement half of 6.3 remains open.

**On the brief's "submission_type per sequence (initial / variation /
renewal / response-to-query)":** that list conflates two axes, and the
codebase already had one of them. *Variation* and *renewal* describe the
**application** and already drive `submission/@type` through
`Product.registration_type`; *initial* and *response* describe **this
transaction**. They coexist — a variation application's first sequence is
`initial` and its answer to the assessor is `response`, and both are
variations. Folding them together would make one of those two facts
unrepresentable, so the per-sequence field is the eCTD
`submission-unit/@type` and takes the EU regional DTD's own enumeration
(verified equal to it, not retyped from memory). The pre-existing
`SubmissionType` was **not** reused: it means multisource vs new chemical
entity, a third axis again.

**Deliberately deferred:** the build does not move a sequence to BUILT
automatically. It is defensible either way — a status the build sets is one
a human cannot forget, but coupling the builder to workflow state is a
decision worth making on its own rather than smuggling into this phase.


### Phase 4a — shared eCTD layer brought to the ICH/FDA specs

A sub-phase of gap.md Phase 4 (the FDA backbone). Reading FDA's Module 1
backbone spec v2.6 and the ICH eCTD spec v3.2.2 for Phase 4 found the
shared lifecycle and backbone code disagreeing with both, so it was fixed
first: FDA could not be built correctly on top of it without changing EU
output anyway. Full account in `reference/build-log.md`.

**4. Publishing engine** — three deviations, all present in EU packages
since P09:
- `modified-file` named the earlier **PDF**; ICH says it names the earlier
  **backbone file** plus the leaf ID (`../0001/index.xml#a1234567`).
- index.xml never referenced the regional backbone, so **no checksum
  covered `eu-regional.xml`**; ICH requires that leaf (always `new`), and
  it is now written.
- Regional hrefs were written from the sequence root; FDA's spec and EMA's
  own `eu-regional.xsl` both resolve them from the regional file's folder.
- Also: a `delete` leaf now carries no href and an empty checksum (ICH).

**5. Validation engine** — M07/M09 now check the ICH form and require the
target leaf to be in the *same* backbone file; M06 no longer exempts the
regional file. Packages built before this fix now report M07/M06 — which is
true of them; a rebuild clears it.

**6. Submission lifecycle management — a bug fixed.** A document left
unchanged in one sequence and replaced in a later one had its
`modified-file` aimed at the immediately prior sequence, whose backbone
never mentioned it. Two-sequence tests could not see it. The resolver no
longer takes the prior sequence number at all: the leaf ID carries its own
sequence (`sequence_number_of`). Regression:
`test_a_document_replaced_after_sitting_unchanged_validates_cleanly`, three
real EU builds judged by the real validator. No migration —
`SequenceLeaf.modified_file` now stores the target leaf ID, and old rows
still read correctly.

### Phase 4b — the FDA backbone

The second real publishing backbone, per ADR 0001: **FDA, eCTD v3.2.2, US
regional Module 1**. Full account in `reference/build-log.md`.

**1. Regulatory data model** — three nullable columns (migration
`a7d4c1f09e62`): `applicant.duns_number`, `project.application_number`,
`project.fda_application_type` (NDA/ANDA/BLA). On `Project` only until gap
Phase 6's `Application` entity exists to receive them. Nothing is backfilled
and nothing is defaulted: the agency issues the number, and FDA's
999999999 D-U-N-S allowance is the filer's statement to make.

**3. Dossier / CTD workspace** — `FDA_PROFILE` registered: cover letter →
FDA 1.2, SmPC and leaflet → 1.14.1.3 draft labeling text, labels → 1.14.1.1.
No certificate or declaration slot (FDA's Module 1 has no heading for a CPP
or a power of attorney). New `RegionProfile.absent_module1_sections`: FDA
has no 1.2.2 registration form, and `expand_sections` never emits it — the
absence is the region's statement, because the EU files that same section.

**4. Publishing engine** — `m1/us/us-regional.xml`, built and validated
against FDA's own `us-regional-v3-3.dtd`, with FDA's fixed header and the
admin block (D-U-N-S, contact, application number/type, submission-id /
sequence-number). The EU-only `if` in `backbone.py` is replaced by a region
table; NAFDAC's refusal now names the CTD endpoint. FDA's DTD accepts any
string where a code goes, so FDA's seven code lists are vendored in
`reference/ectd_dtd/fda-code-lists/` and every code the builder can write
is tested active — and, for application type, tested to MEAN what our enum
says.

**5. Validation engine** — R34 and R35 (FDA-only). The mechanical checks do
not yet understand an FDA package (region-aware M02, M13 for codes): Phase 4c.

**6. Submission lifecycle management** — FDA sequences start at 0001
(`RegionProfile.first_sequence_number`). An FDA amendment's submission-id is
the original application's sequence, which is how FDA's review tool groups
them; a second `initial` sequence is refused with the value to use instead.

**Deliberately not done:** supplements (CMC/labeling/efficacy), grouped
submissions, an upload slot for FDA's own forms (356h, 3794, 3674), and UI
fields for the FDA identifiers (API-only for now).

### Phase 4c — FDA validated, worked through, and reachable from the UI

**5. Validation engine** — the mechanical checks stop assuming the EU. They
find a package's regional backbone by where it sits, so M02 checks
`us-regional.xml` against FDA's DTD as it always checked `eu-regional.xml`
against the EU's. New **M13**: every code in a built FDA package is "active"
in FDA's code lists. It re-reads the ARTIFACT, which is the P06/P10 split
again: 4b's tests prove what the builder writes, M13 proves what the stored
package says. Tested with a DTD-valid backbone carrying
`application-type="banana"`, and with a code FDA has (in the test) retired.

**4. Publishing engine** — an FDA worked example: the full amlodipine
dossier, re-targeted by `app/seed/fda.py` as an ANDA (seed identifiers
chosen so they can never be mistaken for a real application), passes
M01-M13 with no ERROR. A three-sequence FDA lifecycle (original
application, then two amendments touching both backbones) passes every
mechanical check against its predecessors, with amendments' submission-id
pointing at the original application.

**6. Submission lifecycle management** — a sequence's transaction type
(P27's `submission_unit_type`) can now be stated when the sequence is
CREATED. It could only be PATCHed afterwards, so the UI's
create-then-build filed every sequence as `initial`: EU responses told the
agency they were fresh submissions, and FDA refused every build after the
first.

**Web UI** — D-U-N-S number on the applicant (wizard and Module 1),
application number and type on FDA projects (wizard and a Module 1 card),
and a "the next sequence is" select on the Build tab defaulting to
`initial` for a project's first sequence and `response` after. Verified by
driving a real browser against a real API: R34's three findings cleared
from the Module 1 card, then sequences 0001 and 0002 built from the Build
tab. That run also found that the Declarations card offered to sign and
notarise documents FDA's package never files; it now says so, from the
region's own slot list. And a refused build no longer burns a sequence
number: the Build tab retries the sequence it created rather than making
another -- within the page. An unbuilt sequence from an earlier visit is
still on file, because nothing records that a sequence was built (Phase 3's
deferred auto-BUILT).

### Phase 5a — ICH file names, and the checks that hold them

**4. Publishing engine — every package the platform built was
non-conformant.** Measured before any check was written: in the full
amlodipine dossier, 67 of 87 EU files (66 of 73 FDA) were named after their
section number (`3.2.P.1.pdf`), which ICH v3.2.2 Appendix 2 lists as
incorrect twice over (a full stop inside a name, uppercase). Four
certificate and declaration names exceeded 64 characters on a full UUID,
and one excipient path reached 167 characters against FDA's 150, because
the subject appeared twice (folder and file name). Names now come from one
module, `app/ctd/naming.py`: `3-2-p-1.pdf`, the subject only in its folder
(abbreviated with a hash past 24 characters), placeholders as type plus an
8-character id. The instance KEY -- lifecycle section key, upload storage
key -- is unchanged, so existing projects' lifecycles are unaffected: an
unchanged leaf keeps its old path in its old sequence; a changed one is
filed under the new name with an ordinary replace. Both builders now refuse
two leaves at one path instead of silently keeping the last.

**5. Validation engine** — M14 (ICH characters, one extension), M15
(64-character names), M16 (the region's path limit, carried on the
region's `RegionalBackbone` beside its DTD: FDA 150 from its conformance
guide, EU 180 from EMA's harmonised guidance as quoted -- EMA's site is
unreachable from the build environment -- and ICH's 230 otherwise). The
checks spell the ICH rule out themselves rather than import the builder's
naming code, so they cannot agree with it by construction. A structural
test walks the real folder map with an absurdly long subject and proves
every path fits FDA's 150; `SUBJECT_MAX_LENGTH` is trusted only because of
it.

### Phase 5b — a report a person can read, and R31 said plainly

**5. Validation engine.**
- *Report:* `GET /projects/{id}/validation-report` returns the findings as a
  PDF, built by `app/validation/report_pdf.py` through the same python-docx
  → `convert_docx_to_pdf` path the table of contents uses (no new
  dependency). Readiness findings by default; `?sequence_id=` renders that
  sequence's consolidated eCTD validation. It renders, it does not judge:
  the findings and verdict are exactly those the JSON endpoints return.
  Waived checks get their own section, with the reason a human recorded,
  because a package built over a waived ERROR is otherwise indistinguishable
  from one that passed. Verified in a real browser: the download saves as
  `validation-report-examox.pdf` -- which needed `Content-Disposition`
  added to the CORS `expose_headers`, since a cross-origin script cannot
  otherwise read that header (httpx-based tests never see CORS).
- *R31:* declared a tripwire in the registry (`tripwire=True`, new in the
  engine), with a general test holding every tripwire silent on every seed
  (clean and planted-defect) in every region, and R31's existing forcing
  test proving it still fires. gap.md offered "intentionally disabled";
  keeping it armed and declared was chosen instead (see the rule's
  docstring for why).

**Web UI** — "Download report (PDF)" on the Validation tab.


### Fix after Phase 5 — LibreOffice process leak

**8. Test coverage & reliability** (and a production defect under it). The
recurring `test_shutting_down_a_listener_leaves_no_orphaned_libreoffice`
failure traced to two real bugs in the listener's teardown
(`app/assembly/converter.py`): LibreOffice's `oosplash` launcher can block
SIGTERM, and shutdown escalated to SIGKILL only if `unoserver` refused to
die; and after a listener crash the group id was looked up from the dead,
reaped leader, so the crashed listener's LibreOffice kept running beside
its replacement. The group id is now recorded at spawn, a dead
predecessor's group is torn down before a restart, and the group always
gets SIGKILL after a grace period. The count test now counts live
processes (this devcontainer's non-reaping PID 1 makes zombies permanent),
and a new test reproduces a SIGTERM-ignoring group member without
LibreOffice -- the old logic, replayed against it, left it alive.


### Phase 6a — the organization is the unit of access

**1. Regulatory data model.** New `organization` table; `user`, `product`
and `applicant` carry `organization_id`; `user` gains `is_superadmin`
(migration `c5b8e2d4f071`). `owner_id` survives on product and applicant,
demoted to *who created the row* — an audit fact no access check reads.
Recorded in
[docs/decisions/0004-organization-tenancy.md](docs/decisions/0004-organization-tenancy.md),
including the four decisions the project owner made for this phase.

**7. CLI / API surface.** Every ownership check moved from
`owner_id = :user` to `organization_id = :user_org` — 17 call sites across
`deps.py`, the product/applicant/project routers, the child-router factory
and the three result routers. New: `POST /admin/users` (an org admin adds a
colleague — the only way into an existing organization, since registering
always creates a new one) and `/superadmin/*` (organizations with their
first admin, and accounts across organizations). `/admin/users` is now
scoped to the caller's organization; another organization's account 404s,
the same rule the dossier routes use. `/kb/ingest` moved from
`require_admin` to `require_superadmin`: the knowledge base is global and
the org-admin role is now self-service, so it could no longer gate it.
`scripts/promote_admin.py` grants `is_superadmin` instead of a global role.

**8. Test coverage & reliability.** `test_ownership.py` extended, not
loosened: every stranger probe runs twice (another organization, and a
super-admin of another organization), and every probe the owner replays a
COLLEAGUE now replays too — a check still comparing user ids passes the
whole file without that mirror. New `test_superadmin_api.py` ends on the
"accounts only" half: a super-admin gets the stranger's 404 on another
organization's product. The migration's backfill is asserted against rows
inserted at the previous revision, including the downgrade restoring the
old roles.

**Web UI** — sign-up takes an optional organization name; the Users page
names the organization it is managing and has an "Add a colleague" form.
The super-admin has no UI by decision (see the ADR's consequences).

**2. Document management / 3. Dossier workspace / 4. Publishing engine /
5. Validation engine / 6. Submission lifecycle** — unchanged.
