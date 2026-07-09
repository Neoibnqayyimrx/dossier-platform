# P07 — Document Assembly + PDF (DOCX→PDF, bookmarks, granular leaves)

**Before starting:** read `AGENTS.md` (§3, §5 idempotency) and `/reference/ectd-backbone-architecture.md` (PDF rules & granularity, checksum determinism). Depends on P04–P06.

## Goal

Convert approved section DOCX files into eCTD-grade, **granular** PDFs — text-searchable, bookmarked, deterministic — ready to be placed by the CTD builder (P08) and referenced by the eCTD backbone (P09). Determinism is critical: checksums in P09 depend on byte-stable PDFs.

## Tasks

1. **DOCX→PDF** (`services/assembly/pdf.py`) via **LibreOffice headless** (`soffice --headless --convert-to pdf`). Wrap it so it's callable from the API worker; run it in its own container/process if needed. Handle fonts so output is consistent.
2. **Determinism:** normalize PDF output so the same input yields byte-identical bytes — strip/pin creation timestamps and document IDs (post-process with `pypdf`/`PyMuPDF` to set fixed metadata and remove volatile fields). Add a test that converting the same DOCX twice yields identical MD5.
3. **Bookmarks & structure** (`PyMuPDF`): generate bookmarks from document headings; ensure text-searchable output (no rasterization of text). Enforce the PDF rules from the reference doc: no encryption, embedded fonts, letter size where the region requires it, reasonable margins.
4. **Granularity:** produce **one PDF per CTD leaf** as defined by the section map — do **not** merge modules into mega-PDFs. Provide a controlled merge utility only for the specific cases that legitimately need it (e.g. a single multi-part document), never wholesale.
5. **Assembly orchestrator** (`services/assembly/assemble.py`): given a project, iterate the section map, render (P04) → fill approved narrative (P05) → convert to leaf PDFs, and return a **leaf inventory**: list of `{section, title, storage_path, md5, filename}`. This inventory is the shared input to both P08 and P09.
6. **Gate on validation:** refuse to assemble if P06 reports unresolved errors (unless overridden).
7. **Tests:** the demo project assembles to a leaf inventory; each leaf PDF is text-searchable and bookmarked; re-assembly is byte-identical (stable MD5); no mega-PDF is produced.

## Definition of done

- Approved sections convert to deterministic, searchable, bookmarked, granular leaf PDFs.
- Assembly emits a leaf inventory with stable MD5s.
- Repeated assembly is byte-identical; validation gates assembly.

## Do NOT

- Merge whole modules into single PDFs (violates granularity).
- Allow non-deterministic PDF metadata (breaks P09 checksums).
- Rasterize text pages.

## On completion

Tick **P07** in `AGENTS.md` §7; append to `reference/build-log.md`, noting how you achieved byte-stable PDFs.
