# Regulatory Scope: NAFDAC vs FDA/EMA — and why we build NAFDAC first

*Snapshot as of mid-2026. Always re-verify against the agency's own site before a real submission.*

## The key distinction: CTD vs eCTD

- **CTD** = the *content and organization* standard (ICH M4): 5 modules, defined section numbering (e.g. 3.2.P.1). A CTD can be delivered as organized folders of PDFs plus a table of contents.
- **eCTD** = the *electronic transport* standard (ICH M2/M8): CTD content **plus** an XML backbone, per-file MD5 checksums, sequence numbering, and lifecycle operation attributes, validated against agency criteria at a gateway.

A folder tree of nice PDFs with a TOC is a **CTD** (or "NeeS"-style). It is **not** an eCTD. This distinction is the whole reason our build is phased.

## NAFDAC (Nigeria) — our MVP target

- Registration runs through the **NAPAMS portal** (NAFDAC Automated Product Administration and Monitoring System, `registration.nafdac.gov.ng`).
- Applicants submit **one application/dossier per product** and prepare a **CTD dossier** (administrative, quality, non-clinical, clinical) plus an application letter to the Director-General and notarized/legalized declarations and certificates.
- There is **no XML-backbone eCTD requirement**: you assemble a structured CTD and upload it to the portal.
- **Implication for us:** the realistic, least-brittle first deliverable is a well-organized **CTD package** — correct module/section folders, correctly named PDFs, a generated TOC, and the required Module 1 administrative documents for Nigeria. No XML backbone, no MD5 leaves, no lifecycle attributes required. This is genuinely useful and shippable on its own.

> Re-verify: NAFDAC periodically updates guidelines and the NAPAMS workflow. Confirm the current dossier format, required Module 1 documents, and any move toward eCTD on the NAFDAC guidelines page and the NAPAMS portal before submitting.

## FDA (US) — eCTD, "hard mode"

- eCTD is the **mandatory** electronic format for NDAs, ANDAs, BLAs, and commercial INDs (and all subsequent submissions to them, plus DMFs).
- Submissions go through the **Electronic Submissions Gateway (ESG)**; packages that fail backbone/validation are **rejected before a reviewer sees them**.
- **eCTD v4.0** (HL7 RPS) has been accepted for *new* applications since **16 September 2024**, but **both v3.2.2 and v4.0 remain valid** as of 2026. Forward compatibility for existing v3.2.2 applications is not yet available, and no "v4.0 only" mandatory date has been finalized.
- FDA validates incoming packages with a commercial validator (Lorenz eValidator) against published validation criteria; FDA's own rules are stricter than some private tools.
- Module 1 is **US-specific**: FDA fillable forms (e.g. 1571, 356h), electronic signatures, prescribing information/labeling. Scanned form images are not accepted.
- PDF specs: letter size (8.5×11"), ≥1" margins, ≥12-pt body text, text-searchable (not scanned), with bookmarks and hyperlinks.

**Implication for us:** target **eCTD v3.2.2** for the first eCTD build (widest compatibility, mature tooling), with v4.0 as a later, separable phase.

## EMA (EU) — eCTD, mandatory

- eCTD is **mandatory** for all EU/EEA procedure types (centralised, decentralised, mutual recognition, national) and for ASMFs.
- Regional backbone is **EU-specific** (`eu-regional.xml`), Module 1 differs from FDA.
- Submitted via the EMA/NCA eSubmission gateway/web client.

**Implication for us:** EU support = the same v3.2.2 backbone engine + an EU **region profile** (EU Module 1 structure, `eu-regional` DTD). Region differences are configuration, not a rewrite. This is why Phase 09 is built around a pluggable *region profile*.

## What harmonizes across all three

**Modules 2–5** are common across ICH regions (ICH M4Q/M4S/M4E). Only **Module 1** is regional. So the platform prepares Modules 2–5 once and swaps Module 1 + the transport wrapper per region. Our data model and templates lean on this: build the common core once, parametrize the region.

## The resulting build strategy

1. **CTD content core** (Modules 1–5 as templated, data-driven documents) — reused by every target.
2. **NAFDAC CTD package builder** (folders + TOC + Nigeria Module 1) — MVP, ships alone.
3. **eCTD v3.2.2 backbone builder** consuming the same assembled documents — adds XML, checksums, sequences, lifecycle; region profile selects FDA or EU Module 1 + regional DTD.
4. **eCTD v4.0 (RPS)** — later.

The expensive, fiddly, gateway-blocking 20% (the XML backbone, checksums, lifecycle, validation) is isolated in phases 09–10 so the useful 80% (phases 01–08) delivers value first.
