"""Seed the LAMOX project from the real dossier.

Two variants of the 3.2.P.1 narrative are provided:
- BUGGY: mirrors the real dossier (has the 250mg typo, 'Tablets', and a
  leftover 'LATRIM' reference) so the rule engine has real bugs to catch.
- CORRECTED: the fixed version, so we can show a clean pass.

Everything else reflects LAMOX's actual, non-confidential label facts.
"""
from __future__ import annotations

from app.models import (
    Project, Product, ActiveIngredient, Excipient, Packaging,
    StabilityStudy, ClinicalEntry, BatchFormulaLine, Section,
    DosageForm, RegistrationType, Region, ExcipientFunction,
)

# Real dossier text (trimmed) — note the three planted-but-REAL defects.
BUGGY_P1 = """
3.2.P.1 Description and Composition of drug product

Description: Maroon cap / yellow body hard gelatin capsules printed "LAMOX"
and "500", containing almost white powder.

Composition: Each capsule contains Amoxicillin Trihydrate BP equivalent to
Amoxicillin 250mg. Excipients: q.s.

Batch Size: 250,000 Tablets.

(cross-reference: see LATRIM 960 table of contents for layout)
"""

# The corrected version: 500 mg, capsules, no foreign product reference.
CORRECTED_P1 = """
3.2.P.1 Description and Composition of drug product

Description: Maroon cap / yellow body hard gelatin capsules printed "LAMOX"
and "500", containing almost white powder.

Composition: Each capsule contains Amoxicillin Trihydrate BP equivalent to
Amoxicillin 500mg. Excipients: q.s.

Batch Size: 250,000 capsules.
"""


def build_lamox(buggy: bool = True) -> Project:
    project = Project(name="LAMOX renewal", region=Region.NAFDAC)

    product = Product(
        brand_name="LAMOX",
        generic_name="Amoxicillin",
        strength_mg=500,
        dosage_form=DosageForm.CAPSULE_HARD,
        shelf_life_months=24,
        storage_statement="Store below 30 C. Protect from direct sunlight.",
        registration_type=RegistrationType.RENEWAL,
        country="Nigeria",
    )
    project.product = product

    product.apis.append(ActiveIngredient(
        inn_name="Amoxicillin",
        salt_form="Amoxicillin Trihydrate",
        salt_factor=1.148,          # trihydrate/base mass ratio
        compendial_std="BP",
    ))
    product.excipients.extend([
        Excipient(name="Starch", function=ExcipientFunction.DILUENT,
                  grade="BP", compendial_status="BP"),
        Excipient(name="Magnesium Stearate", function=ExcipientFunction.LUBRICANT,
                  grade="BP", compendial_status="BP"),
        Excipient(name="Gelatin capsule shell", function=ExcipientFunction.CAPSULE_SHELL,
                  grade="BP", compendial_status="BP"),
    ])
    product.packaging.extend([
        Packaging(role="primary", description="Aluminium foil + PVC blister"),
        Packaging(role="secondary", description="Printed carton with leaflet"),
        Packaging(role="tertiary", description="7-ply corrugated shipper"),
    ])
    product.stability.append(StabilityStudy(
        condition="long-term 30C/65RH", duration_months=24,
        result_summary="Within specification through 24 months.",
    ))
    product.clinical.append(ClinicalEntry(
        kind="bioequivalence",
        reference_product="Reference amoxicillin 500 mg capsule",
        summary="Comparative BA/BE study; bioequivalence demonstrated.",
    ))
    product.batch_formula.append(BatchFormulaLine(
        component="Amoxicillin Trihydrate BP (equiv. to Amoxicillin 500 mg)",
        is_active=True, spec="BP",
        qty_per_unit_mg=500.0, batch_size_units=250_000,
        declared_batch_qty_kg=144.0,
    ))

    p1_text = BUGGY_P1 if buggy else CORRECTED_P1
    project.sections.append(Section(
        number="3.2.P.1", title="Description & Composition", narrative_text=p1_text,
    ))
    # a second section representing the leftover TOC file reference (real)
    if buggy:
        project.sections.append(Section(
            number="1.1", title="Table of Contents",
            narrative_text="Table of content (Modules 1-5). LATRIM 960 layout reused.",
        ))
    return project
