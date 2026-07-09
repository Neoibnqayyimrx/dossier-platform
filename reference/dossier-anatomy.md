# Dossier Anatomy — a guided tour of the CTD, Modules 1–5

*A learning reference. For each part: what it is, why it exists, and what a reviewer looks for. Structure follows ICH M4. Modules 2–5 are common across ICH regions; Module 1 is regional.*

## The mental model first

A dossier answers one question in a structured way: **"Is this product safe, effective, and of consistent quality — and can you prove it?"** The CTD organizes the evidence into a pyramid:

- **Module 1** — regional paperwork (who's applying, forms, labeling). *Not* part of the common scientific dossier.
- **Module 2** — the **summaries and overviews**: the reviewer's map to everything below.
- **Module 3** — **Quality** (chemistry, manufacturing, controls — "CMC").
- **Module 4** — **Nonclinical** (animal/lab pharmacology and toxicology).
- **Module 5** — **Clinical** (human data).

Modules 3–5 hold the raw evidence; Module 2 summarizes it; Module 1 wraps it for a specific agency. A reviewer reads Module 2 to orient, then drills into 3/4/5 to verify. **Everything is cross-referenced** so a claim in a summary can be traced to its data. That traceability is why eCTD adds hyperlinks and a backbone.

---

## Module 1 — Regional / Administrative (region-specific)

Not "common" — each agency defines its own. Broadly it contains:

- **Cover letter** — what's being submitted and why (new application, renewal, variation).
- **Comprehensive table of contents** — across all modules.
- **Application/registration forms** — the agency's official forms (FDA 356h; NAFDAC's registration forms; EU application form).
- **Product information / labeling** — SmPC/prescribing information, patient leaflet (PIL), packaging/artwork, mock-ups.
- **Certificates and administrative documents** — e.g. Certificate of Pharmaceutical Product (CPP), GMP certificates, manufacturing licences, trademark/registration evidence, power of attorney, declarations.

**NAFDAC specifics** (your MVP target): cover letter to the Director-General, registration forms, CPP, GMP evidence, trademark, licences, and notarized/legalized declarations — uploaded via NAPAMS. **Why it exists:** the agency needs to know *who* is legally responsible, *what* exactly is being registered, and *how* the product will be presented to patients. **Reviewer looks for:** correct current forms, valid unexpired certificates, labeling consistent with the technical data (a strength on the label must match Module 3).

---

## Module 2 — Summaries and Overviews (common)

The reviewer's executive layer. Sections:

- **2.1** CTD table of contents.
- **2.2** Introduction — product, class, proposed indication, dosage form/strength.
- **2.3 Quality Overall Summary (QOS)** — a summary of Module 3. Follows Module 3's structure (S then P).
- **2.4 Nonclinical Overview** — a critical assessment of Module 4.
- **2.5 Clinical Overview** — a critical assessment of Module 5.
- **2.6** Nonclinical written and tabulated summaries.
- **2.7** Clinical summary.

**Why it exists:** no reviewer reads thousands of pages cold. Module 2 lets them understand the whole case, spot issues, and navigate to the supporting data. **Reviewer looks for:** summaries that faithfully reflect the underlying modules — a QOS claiming a 36-month shelf life must be backed by Module 3 stability data. (This is exactly the kind of cross-consistency the P06 rule engine enforces mechanically.)

---

## Module 3 — Quality / CMC (common) — the heart of a generic dossier

Organized into **Drug Substance (S)** and **Drug Product (P)**.

### 3.2.S — Drug Substance (the API)
- **S.1 General Information** — nomenclature, structure, general properties.
- **S.2 Manufacture** — manufacturer(s), process, controls, materials.
- **S.3 Characterisation** — structure elucidation, impurities.
- **S.4 Control of Drug Substance** — specification, analytical procedures, validation of those procedures, batch analyses, justification of specification.
- **S.5 Reference Standards.**
- **S.6 Container Closure System.**
- **S.7 Stability.**

*(Often the API maker's confidential detail lives in a separate **DMF/ASMF** referenced here, not in your dossier — a key redaction/confidentiality point.)*

### 3.2.P — Drug Product (the finished product)
- **P.1 Description and Composition** — dosage form, full composition (this is a *data table*, not prose).
- **P.2 Pharmaceutical Development** — why the formulation is what it is.
- **P.3 Manufacture** — the finished-product process, batch formula, controls.
- **P.4 Control of Excipients.**
- **P.5 Control of Drug Product** — specification, analytical procedures + their validation, batch analyses, impurities.
- **P.6 Reference Standards.**
- **P.7 Container Closure System.**
- **P.8 Stability** — the data that *justifies the shelf life and storage statement*.

### 3.2.A Appendices (facilities/equipment, adventitious agents, excipients) · 3.2.R Regional Information · 3.3 Literature References

**Why it exists:** to prove the product can be made **consistently to a defined quality**, batch after batch. **Reviewer looks for:** the specification, analytical method validation, batch data, and stability all telling one coherent story — and consistency with the label and QOS. **For the software:** most of Module 3 is *structured data + tables* (composition, specs, batch analyses, stability) — highly deterministic and template-driven (P04). Narrative is limited (P.2 development rationale, some justifications). This is why the "AI writes prose only" boundary works so well here.

---

## Module 4 — Nonclinical Study Reports (common)

- **4.1** TOC · **4.2** Study reports: pharmacology, pharmacokinetics, toxicology · **4.3** Literature references.

**Why it exists:** animal/lab evidence of safety and biological activity before/alongside human use. **For generics** of well-established substances, Module 4 is often **satisfied by literature references** rather than new studies, because the substance's nonclinical profile is already established. **Reviewer looks for:** adequate safety coverage for the proposed use, or a sound literature-based justification for its absence.

---

## Module 5 — Clinical Study Reports (common)

- **5.1** TOC.
- **5.2** Tabular listing of all clinical studies.
- **5.3** Clinical study reports — organized by type (biopharmaceutic/BA-BE, PK, efficacy, safety).
- **5.4** Literature references.

**Why it exists:** human evidence of efficacy and safety. **For a generic**, the centerpiece is usually the **bioequivalence (BE) study** (typically under 5.3.1): proof the generic behaves in the body like the reference product, plus the reference product's identity. **Reviewer looks for:** a valid BE study meeting acceptance criteria against a proper reference, with the reference product clearly identified. (This maps to your `Clinical` entity's bioequivalence + reference-product fields, and to a P06 completeness rule: "generic ⇒ BE required and included.")

---

## How the modules talk to each other (the part software makes easy)

- Label strength (M1) ↔ product strength (M3 P.1) ↔ QOS (M2.3).
- Shelf life / storage statement (M1 labeling, M2.3) ↔ stability data (M3 P.8).
- Reference product (M1 labeling context) ↔ BE study reference (M5.3).
- API specification (M3 S.4) ↔ finished-product impurity control (M3 P.5).

Every one of these links is a place a reviewer checks for consistency — and therefore a place the **deterministic rule engine (P06)** should check automatically. When you post your real dossier, tracing these links through an actual document is the single most useful exercise for understanding both the domain and why the platform is built the way it is.

## Quick self-check questions

1. Which module is *not* common across regions, and why does that matter for the eCTD regional backbone?
2. In a generic tablet dossier, where does the bioequivalence study live, and which data entity in our model represents it?
3. Give two cross-module consistency checks a reviewer performs that our P06 engine should automate.
4. Why is most of Module 3 a good fit for deterministic templates, while Module 2 overviews need more narrative?
5. Where might API-manufacturer confidential information sit *outside* your dossier, and why does that matter when you share a draft?
