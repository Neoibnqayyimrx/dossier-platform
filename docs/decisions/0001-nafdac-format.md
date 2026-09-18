# 0001 — NAFDAC's technical format: CTD, not eCTD

- **Status:** Accepted
- **Date:** 2026-09-18
- **Phase:** gap.md Phase 0 (blocks Phase 4)
- **Decision owner:** confirmed against NAFDAC's own current guideline, not assumption

---

## Question

gap.md Phase 4 asks for a "second real publishing backbone" but leaves its target
open, because it depends on a factual question nobody had verified from source:

> Does NAFDAC today require a true eCTD XML backbone (`index.xml`, per-leaf MD5
> checksums, sequence numbering, lifecycle operation attributes), or does it
> require CTD *content and organization* delivered as electronic copies?

The distinction matters because it is the difference between a folder tree of
PDFs plus a table of contents (CTD) and a gateway-validated XML transport
package (eCTD). See `reference/nafdac-vs-fda-ema-scope.md` for the framing.

## Decision

**NAFDAC requires CTD, delivered as electronic documents uploaded to a web
portal. It does not require an eCTD XML backbone.** The existing folder-tree
CTD builder (`backend/app/ctd/`) is already the correct output for NAFDAC.

**Therefore Phase 4 does not build a NAFDAC backbone. Phase 4 targets FDA**, and
specifically **eCTD v3.2.2 with the US regional backbone** — the `us-regional.xml`
gap already named in `backend/app/ectd/backbone.py`.

## Evidence

### Primary source — NAFDAC's own current guideline

*Guidelines for Registration of Imported Drug Products in Nigeria (Human and
Veterinary Drugs)*, Doc. Ref. No. **DR&R-GDL-005-03**, **effective 20/03/2025,
review date 21/03/2030** — i.e. this is the in-force document today, not a
superseded one.

What it says about format and transport:

> "The Application for the registration of all drug products should be processed
> on the NAFDAC Automated Product Administration and Monitoring System (NAPAMS)
> portal - https://registration.nafdac.gov.ng."

> "The following documents are uploaded on the NAPAMS portal. After successful
> submission, all original documents will be presented upon request."

> "Bioequivalence study report/Biowaiver data shall be submitted on DMS using the
> **CTD Dossier format**."

What it does **not** say, and this is the load-bearing evidence: a full-text
search of all 12 pages returns **zero occurrences** of `eCTD`, `XML`,
`backbone`, `checksum`, `MD5`, or `sequence`. An agency that required an XML
backbone would have to specify it — the backbone is not something an applicant
can infer. Its total absence from the in-force registration guideline is a
negative result strong enough to decide on.

The mechanism described throughout is *upload documents to a portal*, with
originals producible on request. That is document management, not eCTD transport.

### Corroborating — the CTD mandate itself

NAFDAC's "Full Implementation of the Common Technical Document (CTD) Format"
notice (published 20 November 2019, effective 1 June 2020) mandates **CTD** for
dossiers supporting Marketing Authorization applications. It likewise makes no
mention of eCTD or an XML backbone. So the mandate that is in force is a mandate
on *content and organization*, and has been since 2020.

### Roadmap check — is an XML backbone coming?

No published NAFDAC roadmap toward an XML-backbone eCTD requirement was found.

NAFDAC's actual modernization direction is a **web-based Dossier Management
System (DMS)**, introduced electronically in 2023, for submitting dossiers in
CTD format through the portal. This is documented in a 2026 paper in
*Therapeutic Innovation & Regulatory Science* ("Web-based Dossier Management
System (DMS) and Emerging Technologies to Facilitate Faster Registration and
Access to Human Drugs: NAFDAC's Experience").

Note an honest limit on this point: the full text of that paper is paywalled and
was not read — the characterization above comes from its abstract/indexing and
from NAFDAC's own guideline. This does not weaken the decision, because the
decision rests on the in-force guideline, but it does mean the roadmap finding is
"no evidence of a plan found" rather than "a plan is confirmed not to exist".

**Re-verification trigger:** if NAFDAC publishes a technical specification
document (as distinct from a registration guideline), or the NAPAMS/DMS user
manual starts specifying file-level structure, revisit this ADR.

## Implication for Phase 4

### What is *not* built

No `NAFDACBackboneBuilder`. Building one would produce a package NAFDAC has no
way to consume and no stated requirement for — pure speculative work, and worse,
it would imply to a user that their NAFDAC filing needs a backbone it does not.

### What is built instead

`FDABackboneBuilder`, or more precisely US regional support inside the existing
`V322BackboneBuilder` — the choice between those two shapes is a Phase 4 design
question, not a Phase 0 one. The reasons FDA is the right second target:

1. **It is already the named gap.** `V322BackboneBuilder.build` raises
   `NotImplementedError` with the message "FDA is not built yet". The code has
   been pointing at this for a phase.
2. **`Region.FDA` already exists** in `backend/app/models/enums.py`, so the
   dispatch target is real, not hypothetical.
3. **FDA genuinely requires eCTD** — it is mandatory for NDAs, ANDAs, BLAs and
   commercial INDs, and packages failing backbone validation are rejected at the
   gateway before review. This is a region where the backbone work actually buys
   something.
4. **v3.2.2 is still valid at FDA.** As of September 2026, FDA supports both
   v3.2.2 and v4.0; v4.0 has been accepted for *new* applications since
   16 September 2024 but is not mandatory and no final cutover rule has been
   announced (industry expects ~2028–2029). So Phase 4 extends the existing
   v3.2.2 engine rather than needing P12 (eCTD v4.0) first. Worth knowing:
   Japan's PMDA mandated v4.0 from 1 April 2026, so v4.0 is no longer purely
   theoretical — but it does not block FDA.

### Known prerequisite Phase 4 must handle

`reference/ectd_dtd/` currently holds only the ICH DTD (`ich-ectd-3-2.dtd`) and
the EU regional set (`eu-regional.dtd`, `eu-envelope.mod`, `eu-leaf.mod`). **The
US regional DTD is not in the repo.** Phase 4 cannot self-validate the US
regional XML the way the EU path does until that DTD is obtained from FDA's
published eCTD specification. This is a real dependency, not a detail — the
EU path's "validate against the DTD before returning" guarantee is the thing that
makes the builder trustworthy, and FDA must get the same treatment.

## Correction to gap.md

gap.md's Phase 4 refers to `backbone.py` and Phase 1/3 refer to paths under
`backend/app/services/ectd/` and `backend/app/services/`. **That directory does
not exist.** The real layout is `backend/app/ectd/` and `backend/app/ctd/` —
services are not nested under a `services/` package, though `AGENTS.md` §4
describes the layout that way. The gate itself is at
`backend/app/ectd/backbone.py:64`. Paths in gap.md should be treated as
approximate and re-verified per phase.

## Consequences

- Phase 4 is scoped to FDA, and inherits a blocking prerequisite (the US
  regional DTD) that should be resolved before the phase starts.
- NAFDAC remains a CTD-only region, and the `NotImplementedError` in
  `backbone.py` stays correct for it — NAFDAC should arguably raise a *clearer*
  error ("NAFDAC does not use an eCTD backbone") rather than the current "not
  built yet", which misdescribes it as unfinished work. Small Phase 4 addition.
- `reference/nafdac-vs-fda-ema-scope.md`'s existing claim — "There is no
  XML-backbone eCTD requirement" — is **confirmed against the current in-force
  guideline** and can lose its "always re-verify" hedge for this specific point,
  dated to this ADR.

## Sources

- NAFDAC, *Guidelines for Registration of Imported Drug Products in Nigeria
  (Human and Veterinary Drugs)*, DR&R-GDL-005-03, effective 20/03/2025 —
  https://nafdac.gov.ng/wp-content/uploads/Files/Resources/Guidelines/DR&R_2025/Guidelines-for-Registration-of-Imported-Drug-Products-in-Nigeria-Human-and-Veterinary-Drugs.pdf
- NAFDAC, *Full Implementation of the Common Technical Document (CTD) Format*
  (#11191) — https://nafdac.gov.ng/full-implementation-of-the-common-technical-document-ctd-format-11191/
- NAFDAC, *FAQs on Dossier Submission* —
  https://nafdac.gov.ng/regulatory-resources/frequently-asked-questions-faqs-on-dossier-submission/
- *Web-based Dossier Management System (DMS) and Emerging Technologies…:
  NAFDAC's Experience*, Ther Innov Regul Sci (2026) —
  https://link.springer.com/article/10.1007/s43441-026-00965-5 (abstract only;
  full text paywalled)
- FDA, *Electronic Common Technical Document (eCTD)* —
  https://www.fda.gov/drugs/electronic-regulatory-submission-and-review/electronic-common-technical-document-ectd
