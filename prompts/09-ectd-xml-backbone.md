# P09 — eCTD v3.2.2 XML Backbone Builder (FDA / EU "hard mode")

**Before starting:** read `/reference/ectd-backbone-architecture.md` **in full** — this phase implements it. Also `AGENTS.md` §2 target #2, §5 idempotency. Depends on P07 (leaf inventory with stable MD5s) and P08 (folder structure concepts).

## Goal

Wrap the same assembled leaf inventory in a valid eCTD **v3.2.2** transport layer: sequenced folders, ICH `index.xml`, regional backbone, `index-md5.txt`, per-leaf MD5 checksums, and lifecycle operation attributes. Built behind an interface so v4.0 (P12) can slot in later.

## Tasks

1. **`BackboneBuilder` interface** so `V322BackboneBuilder` (now) and `V4RpsBackboneBuilder` (later) are interchangeable. Region profile (FDA/EU) selects the regional DTD and Module 1 layout.
2. **Sequence scaffolder** (`services/ectd/scaffold.py`): create `<app>/NNNN/` with `m1/<region>/`, `m2`–`m5`, `util/dtd/`, `util/style/`; copy in the correct DTDs and the `ectd-2-0.xsl` stylesheet. Sequence number zero-padded to 4 digits, sourced from the project's `Sequence` records (P01).
3. **Checksum utility** (`services/ectd/checksum.py`): MD5 for any file; write `index-md5.txt` for the finished `index.xml`. Must be deterministic (relies on P07's byte-stable PDFs).
4. **Leaf model → XML** (`services/ectd/leaf.py`): build `<leaf>` elements with `ID`, `operation`, `xlink:href`, `checksum`, `checksum-type=md5`, `modified-file` (when replacing/deleting/appending), and `<title>`. **Use `lxml`; never string-concatenate XML.**
5. **ICH backbone** (`services/ectd/index_xml.py`): construct the heading hierarchy from the CTD section map and hang leaves under the correct headings; produce `index.xml` and **validate it against the ICH DTD** in-process. Fail loudly on DTD violation.
6. **Regional backbone** (`services/ectd/regional.py`): build `m1/<region>/<region>-regional.xml` with the envelope (application number, submission type/sub-type, applicant, agency, sequence, related sequence) from the region profile + project data, validate against the regional DTD. Envelope controlled-vocabulary values come from the region profile config — no magic strings.
7. **Lifecycle resolver** (`services/ectd/lifecycle.py`): given the prior sequence's leaf inventory + the new assembly, compute each leaf's `operation` (`new`/`replace`/`append`/`delete`) and wire `modified-file` to the correct prior-sequence path + ID. This is the highest-risk logic — isolate and test it hard.
8. **Full sequence builder** (`services/ectd/build.py`): scaffold → place leaf PDFs → compute checksums → build both XML backbones → write `index-md5.txt` → package. Idempotent: same inputs → byte-identical sequence.
9. **API**: `POST /projects/{id}/build/ectd?region=FDA` → builds the current sequence, returns a handle + a build report.
10. **Golden-fixture tests:**
    - A known input set → a byte-stable, **DTD-valid** `0000` sequence with correct leaf checksums and `index-md5.txt`.
    - A follow-up `0001` that **replaces exactly one leaf**, with `modified-file` correctly targeting the `0000` leaf and `operation=replace`, others untouched.
    - Tampering with a leaf file changes its checksum (proves checksums are real).

## Definition of done

- The demo project builds a DTD-valid `0000` eCTD sequence (FDA profile) with correct MD5 leaves and `index-md5.txt`.
- A second sequence correctly performs a single-leaf `replace` with valid `modified-file` targeting.
- Builds are deterministic; both backbones validate against their DTDs.

## Do NOT

- Merge leaves into mega-PDFs (granularity — see reference doc).
- Hand-write XML strings — `lxml` only, DTD-validated.
- Claim "gateway-ready" from DTD validity alone — business-rule validation is P10.

## On completion

Tick **P09** in `AGENTS.md` §7; append to `reference/build-log.md`, noting which DTD versions and region profiles you implemented.
