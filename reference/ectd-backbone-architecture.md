# eCTD XML Backbone Architecture (v3.2.2), with notes on v4.0

*Technical reference for Phase 09/10. This is the part a naive "folders + PDFs + TOC" design gets wrong.*

## Mental model

An eCTD is **not** a snapshot of a dossier. It is a **cumulative, lifecycle-managed record of changes** to a dossier over time. Each submission is a **sequence** that says, in XML, "add this leaf", "replace that earlier leaf", "delete this one". A reviewer's tool replays every sequence to reconstruct the current view. That's why the backbone, checksums, and operation attributes are load-bearing — they are the diff/version-control layer of the whole system.

If you build a folder tree of PDFs and stop, you have a CTD, not an eCTD. The backbone below is the difference.

## Physical structure of one sequence (v3.2.2)

```
<application>/
└── 0000/                          # sequence number, 4 digits, zero-padded
    ├── index.xml                  # ICH backbone (conforms to ich-ectd-3-2.dtd)
    ├── index-md5.txt              # MD5 hash of index.xml (single line)
    ├── util/
    │   ├── dtd/                    # ich-ectd-3-2.dtd + regional DTD
    │   └── style/                  # ectd-2-0.xsl stylesheet
    ├── m1/
    │   └── us/                     # region folder (us / eu / etc.)
    │       ├── us-regional.xml     # regional backbone (regional DTD)
    │       └── ... (region M1 leaf PDFs)
    ├── m2/
    ├── m3/
    │   └── 32-body-data/... (granular leaf PDFs)
    ├── m4/
    └── m5/
```

The **next** submission is a sibling folder `0001/`, then `0002/`, etc. Earlier sequences are never edited — new sequences reference them.

## The ICH backbone: `index.xml`

- Conforms to the ICH eCTD DTD (`ich-ectd-3-2.dtd`). **Always build with `lxml` and validate against the DTD** — never string-concatenate.
- Contains an **envelope** identifying the application (agency, submission type, sequence number, etc. — envelope content is largely defined by the *regional* spec).
- Contains a hierarchy of CTD **headings** (m1…m5, then sub-sections) matching the CTD numbering.
- Under headings sit **leaf** elements — one per physical file.

### The `leaf` element (the heart of it)

Each leaf carries:

| Attribute / child | Meaning |
|---|---|
| `ID` | unique leaf identifier within the submission |
| `operation` | `new` \| `replace` \| `append` \| `delete` — the lifecycle action |
| `xlink:href` | relative path to the physical file (e.g. `m3/32-body-data/.../spec.pdf`) |
| `checksum` | the file's **MD5** hash |
| `checksum-type` | `md5` |
| `modified-file` | for `replace`/`delete`/`append`: relative path (into a **previous sequence**) of the leaf being acted upon, plus that leaf's `ID` |
| `<title>` | human-readable leaf title shown in the reviewer's navigation |

### Lifecycle operations — the whole point

- **new** — first appearance of a document.
- **replace** — supersedes a specific earlier leaf (points at it via `modified-file`). The old one stays on disk in its old sequence; the backbone just marks it replaced.
- **append** — adds content related to an earlier leaf without replacing it.
- **delete** — retires an earlier leaf from the current view.

Get `modified-file` targeting or checksums wrong and the submission fails validation at the gateway. This is the number-one source of eCTD rejections, so Phase 10 tests it hard.

## The regional backbone

- FDA: `m1/us/us-regional.xml` conforming to the FDA regional DTD (e.g. `us-regional-v X.dtd`).
- EU: `m1/eu/eu-regional.xml` conforming to the EU regional DTD.
- Holds the **envelope** (application number, submission type/sub-type, applicant, agency, sequence, related sequence, etc.) and the Module 1 leaf structure, which differs per region.
- **Controlled vocabularies** constrain many envelope values (submission types, etc.). Load these from the region profile; do not hard-code magic strings.

## Checksums

- Every leaf file → an **MD5** recorded in the backbone.
- `index.xml` itself → its MD5 written to `index-md5.txt`.
- Therefore builders must be **deterministic and idempotent**: same inputs → byte-identical files → stable checksums. Non-deterministic PDF generation (embedded timestamps, random IDs) will break this — pin/normalize it in Phase 07.

## PDF rules that the backbone assumes

- Text-searchable PDFs (not scanned images) where possible; scanned pages at defined resolution.
- Bookmarks and hyperlinks for navigation; bookmarks required for longer documents.
- No encryption/password protection. Fonts embedded. Constrained PDF version.
- **Granularity:** leaves are document-level, not one giant merged PDF. Do **not** merge modules into mega-PDFs — that violates granularity guidance. (This is a common mistake in naive designs.)

## v4.0 (HL7 RPS) — what changes, for later

- Replaces the twin ICH+regional DTD backbones with a **single HL7 RPS XML message**.
- Introduces **UUIDs** for documents, keywords, and **"context of use" (CoU)** — a document is linked to one or more CoUs, enabling reuse and two-way communication.
- Lifecycle operations attach to CoUs rather than leaves-in-headings.
- Controlled vocabularies shipped as separate versioned packages.
- Accepted by FDA for new applications since 16 Sep 2024; not yet mandatory-only.
- **For us:** design Phase 09's builder behind an interface (`BackboneBuilder`) so a `V4RpsBackboneBuilder` can be added later without touching assembly, templating, or validation. Do not attempt v4.0 until v3.2.2 is solid and tested.

## Validation (Phase 10)

Two layers:

1. **DTD conformance** — `index.xml` and the regional XML validate against their DTDs (do this in-process with `lxml`).
2. **Business rules** — the agency's published **validation criteria** (structure, required elements, checksum correctness, operation/`modified-file` integrity, file format, naming). FDA effectively defines "valid" via its validator (Lorenz eValidator) and published criteria; EU via its own criteria.

Our engine implements the mechanical rules we can (checksums, DTD, `modified-file` resolution, granularity, naming, required-leaf presence) and, where feasible, shells out to / integrates an external validator for the authoritative check. Never claim "gateway-ready" from our own checks alone — always recommend a final pass through the agency-recognized validator.

## Minimum viable backbone builder (Phase 09 scope)

Build, test-first, in this order:
1. Sequence folder scaffolder (`m1..m5`, `util/`, region folder).
2. MD5 utility + `index-md5.txt` writer.
3. Leaf model (path, title, operation, checksum, modified-file) → `lxml` element.
4. Heading tree from CTD section map → `index.xml`, DTD-validated.
5. Regional backbone from region profile + envelope data, DTD-validated.
6. Lifecycle resolver: given a prior submission's leaf inventory and the new documents, compute `new`/`replace`/`delete` and wire `modified-file`.
7. Golden-fixture tests: a known set of inputs → a byte-stable, DTD-valid `0000` sequence, then a `0001` that correctly replaces one leaf.
