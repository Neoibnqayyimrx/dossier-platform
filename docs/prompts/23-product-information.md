# P23 — Product information: SmPC, labels, leaflet

**Before starting:** read `docs/target-toc.yaml` (`product_information_model`, leaves 1.3.1–1.3.3), `app/narrative/` in full — especially `guardrails.py` — and `app/models/product.py`. Depends on P21 (shelf life and storage come from stability data).

## Goal

Unblock **3 leaves** — and build the platform's best demonstration of catching a real regulatory defect.

## Why these three matter disproportionately

The Summary of Product Characteristics, the outer and inner labels, and the patient information leaflet say the same things to three audiences. They must agree on strength, shelf life, storage conditions, pack sizes, indications and contraindications.

In practice they routinely do not. They are written at different times by different people, and a shelf life extension updates two of the three. Regulators find it constantly. A platform that renders all three from one dataset makes that class of defect impossible to produce — which is precisely the argument this project exists to make.

## Tasks

### P23a — Product information as data (backend)

1. **A `ProductInformation` model** covering the SmPC section structure: therapeutic indications, posology and method of administration, contraindications, special warnings and precautions, interactions, use in pregnancy and lactation, effects on driving, undesirable effects, overdose, pharmacodynamic and pharmacokinetic properties, preclinical safety, list of excipients, incompatibilities, shelf life, storage conditions, container contents.

   Structured fields, not one text blob. The whole point is that shelf life and storage are *the same values* the stability data and 3.2.P.7 already hold — they must be references, not re-entries. If a field can be derived, derive it.

2. **Register 1.3.1, 1.3.2 and 1.3.3**, all rendering from that single model. The label is generated (it is short and entirely factual); the SmPC and leaflet are hybrid, with narrative slots for prose sections.

3. **The cross-document rules** — the reason for the phase:
   - Strength, shelf life, storage and pack sizes must agree across all three documents *and* with 3.2.P.7 and the stability data. Any divergence is an ERROR naming both values and both locations.
   - Every excipient listed in the leaflet must appear in the batch formula, and vice versa.
   - Contraindications and warnings must be consistent between SmPC and leaflet.

4. **Leaflet readability.** A patient leaflet has plain-language obligations that an SmPC does not. If the narrative generator drafts leaflet text, the guardrails must enforce a different register than for an SmPC. Treat this as a distinct narrative slot type, not the same one with a different prompt.

### P23b — Editing product information (frontend)

5. **A product information step**, organised by SmPC section, with derived fields shown as read-only and labelled with where they come from. A user trying to type a shelf life that contradicts the stability data should see that it is derived, not be allowed to overwrite it and find out at export.

6. **A three-way comparison view** — SmPC, label and leaflet side by side on the shared fields, with divergences highlighted. This is the single most demonstrable screen in the product: it shows a real regulatory defect being caught, in a form a pharmacist recognises immediately.

## Definition of done

- `scripts/check_target_toc.py` gains 3 leaves.
- A test proves a shelf life change in the stability data propagates to all three documents, and that none of them can be made to disagree.
- A test proves an excipient present in the batch formula but absent from the leaflet is caught.
- All three documents render from one dataset with no duplicated entry.

## Build log

Record which fields are derived and which are authored, and how a user is prevented from overwriting a derived one. Record the leaflet register decision.
