# Worked Example — the LAMOX dossier, mapped to the platform

*A real NAFDAC CTD (LAMOX — Amoxicillin 500 mg capsules, Me Cure Industries Ltd, application type: Renewal) used as the reference dossier. This doc turns it into three learning artifacts: (1) a guided tour, (2) the data model reverse-engineered from it, and (3) real validation rules derived from real errors found in it.*

## 1. What this dossier is

- **Product:** LAMOX — brand name; generic **Amoxicillin (as Amoxicillin Trihydrate BP) 500 mg**; **hard gelatin capsule** (size 0, maroon cap / yellow body, printed "LAMOX" / "500").
- **Applicant/manufacturer:** Me Cure Industries Ltd, Oshodi, Lagos.
- **Registration type:** Renewal.
- **Packs:** 10×10's and 2×10's blisters (aluminium foil + PVC).
- **Shelf life / storage:** 24 months; store below 30 °C, protect from sunlight.
- **Excipients:** starch, magnesium stearate, gelatin capsule shell (with approved colours).
- It follows the full CTD Module 1–5 tree, with thin **narrative `.docx`** wrappers and **`.pdf` evidence** (certificates, COAs, specifications, BMR/BPR, validation protocol, stability data, BE study reports).

This is exactly the structure `/reference/dossier-anatomy.md` describes — now made concrete.

## 2. Guided tour: how the real files map to the anatomy

- **Module 1 (regional/admin):** cover letter (1.0), TOC (1.1), application info (1.2.x: application letter, registration form, certificate of incorporation, power of attorney, manufacturing authorisation, trademark, superintendent pharmacist licence, premises registration, evidence of previous marketing authorisation…), product information/SPC (1.3), regional summaries + QIS (1.4), electronic review doc (1.5). **These are the NAFDAC-specific Module 1 slots your region profile (P08) must encode.**
- **Module 2 (summaries):** 2.1 TOC, 2.2 introduction, **2.3 QOS**, 2.4 nonclinical overview, 2.5 clinical overview, 2.6 nonclinical summary, 2.7 clinical summary.
- **Module 3 (quality):** the bulk. `3.2.S` (drug substance: S.1 general info → S.7 stability) and `3.2.P` (drug product: P.1 description & composition → P.8 stability), plus 3.2.A appendices. Supported by real PDFs: API COA/MOA/spec, excipient COA/MOA/spec, finished-product spec, BMR (batch manufacturing record), BPR (batch packaging record), product validation protocol, working-standard cert, stability data.
- **Module 4 (nonclinical):** 4.1 TOC, 4.2 study reports (pharmacology / PK / toxicology), 4.3 literature. As expected for a well-established generic, these are **literature-based**, not new studies — confirming the anatomy doc's point.
- **Module 5 (clinical):** 5.1 TOC, 5.2 tabular listing, **5.3.1 biopharmaceutics = the bioequivalence evidence** (comparative BA/BE for amoxicillin, plasma assay method, IVIVC, BA study reports), 5.3.2–5.3.7 mostly N/A for a generic, 5.4 literature. The centre of gravity is the **BE study**, exactly as predicted for a generic.

**Teaching point:** notice how little of this is free prose. Module 1 is forms + certificates; Module 3 is specs, tables, and attached evidence; Module 5 is attached study reports. The genuinely "narrative" writing is concentrated in the Module 2 overviews and a few Module 3 justifications (P.2 development). **That is precisely the sliver the LLM should write (P05); everything else is data + placement (P01/P04/P07/P08).**

## 3. Reverse-engineering the data model (feeds P01)

From LAMOX's actual content, the P01 entities populate like this:

- **Product:** brand=LAMOX; generic=Amoxicillin; salt=Amoxicillin Trihydrate; strength=500 mg (expressed as base); dosage_form=hard gelatin capsule; pack sizes=[10×10, 2×10]; shelf_life=24 months; storage="below 30 °C, protect from light"; registration_type=Renewal; country=Nigeria; route=oral.
- **Manufacturer:** Me Cure Industries Ltd; site=Oshodi, Lagos; + GMP/authorisation evidence (the 1.2.9 manufacturing authorisation, licences).
- **ActiveIngredient (API):** Amoxicillin Trihydrate; compendial=BP; + spec/COA/MOA (the Module 3 P.5/S.4 evidence); reference/working standard (P.6).
- **Excipient[]:** Starch (BP), Magnesium Stearate (BP), Gelatin capsule shell (BP) — each with function, grade, compendial status, supplier, COA/MOA/spec.
- **Packaging:** primary=aluminium foil + PVC blister; secondary=printed carton; +leaflet, +7-ply corrugated shipper.
- **Stability[]:** the study behind the 24-month shelf life (attached PDF) — model as rows with condition, duration, and result summary.
- **Clinical:** bioequivalence=yes; reference_product=(named in 5.3.1); studies=[comparative BA/BE amoxicillin].
- **BatchFormula (worth adding):** per-unit mg and per-batch quantity for each component at a stated batch size (250,000 caps) — this is the 3.2.P.1 composition table, and it enables real arithmetic validation (below).

**Exercise for you:** open the wizard fields you'd design (P11) and check every one can be filled from LAMOX. Any field you can't fill from a real dossier is probably wrong; any dossier content with no home in the model is a missing field.

## 4. Real validation rules derived from real errors (feeds P06)

This dossier contains genuine copy-paste artifacts — the exact failure mode a generator + validator prevents. Each becomes a deterministic rule:

1. **Strength stated consistently.** In 3.2.P.1 the prose reads "Equivalent to Amoxicillin **250 mg**" while the composition table and everywhere else say **500 mg**. → Rule: the strength in every section's narrative must equal `Product.strength`. *(Real bug caught.)*
2. **Dosage form stated consistently.** 3.2.P.1 says "Batch Size: 250,000 **Tablets**" and "Qty. **Caps**" in the same table — LAMOX is a **capsule**. → Rule: no section may reference a dosage form other than `Product.dosage_form`. *(Real bug caught.)*
3. **No foreign-product references.** The 1.1 TOC folder carries a leftover file named for **"LATRIM 960"** (a different product), and a stray "FDR.docx". → Rule: scan all documents for brand/generic names not belonging to this product; flag cross-product contamination. *(Real bug caught — and the smoking gun that these dossiers are built by copy-pasting a previous product's dossier, which is the whole reason to automate.)*
4. **Salt-to-base arithmetic.** Table lists 500 mg amoxicillin (base) and a batch quantity of 144.00 kg amoxicillin trihydrate for 250,000 caps. Check: 500 mg base × 250,000 = 125 kg base; trihydrate ≈ base × (MW ratio ≈ 1.148) ≈ 143.5 kg ≈ **144 kg ✓**. → Rule: verify per-unit × batch-size, and salt/base overage, reconcile with the stated batch quantity. *(This one is internally consistent — a good example of a rule **passing**, and of why the model needs both base strength and salt factor.)*
5. **Shelf life ≤ stability-supported duration.** SPC states 24 months; the stability study (attached) must support ≥24 months. → Rule from the anatomy doc, now bound to real values.
6. **Storage statement consistency.** "Below 30 °C" in SPC must match the stability study conditions and the label. → cross-section rule.
7. **Completeness for a generic renewal.** BE evidence present (5.3.1 ✓), previous marketing authorisation present (1.2.13 ✓), superintendent pharmacist licence present and unexpired (1.2.11), premises registration present (1.2.12). → completeness rules keyed to registration_type=Renewal.

**Teaching point:** rules 1–3 are the ones that make regulatory teams look bad in front of a reviewer, and they're trivially preventable with deterministic checks. This is the platform's core value proposition, proven on a real document.

## 5. Turning LAMOX into fixtures (feeds P01/P04/P06/P07)

- **Seed data (P01):** replace the toy demo with a LAMOX-derived (sanitized) fixture — same fields, real shape.
- **Templates (P04):** the 3.2.P.1, 3.2.P.8, cover letter, and QOS `.docx` files are ready-made template skeletons — replace product-specific values with `{{ }}` slots and mark narrative regions.
- **Validation fixtures (P06):** two copies of 3.2.P.1 — the original (fails rules 1 & 2) and a corrected one (passes) — are your test pair.
- **Assembly golden test (P07/P08):** the real folder tree is the expected-structure fixture for the NAFDAC builder.

> **Confidentiality note:** this dossier belongs to a real manufacturer and contains real certificates, batch records, and a BE study. Keep it out of any public repo. For fixtures, use **sanitized** derivatives (rename the manufacturer, redact certificate scans, keep only structure and non-confidential label facts). Never ingest the BE study or batch records into the KB (P03) — they're confidential and copyrighted, and the KB is guidance-only anyway.

## 6. Suggested first build move

Use LAMOX to drive **P01 → P04 → P06** as a vertical slice: model LAMOX, template its 3.2.P.1, and write rules 1–3 so the platform catches the three real bugs above on the real content. That single slice teaches the data model, templating, and the rule engine at once — on a document you know intimately.
