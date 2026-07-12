"""Seed the EXAMOX project — our own company's (EXAGON) product.

Same structure as app/seed/lamox.py (see reference/worked-example-lamox.md for
the provenance of that pattern): two variants of the 3.2.P.1 narrative so the
rule engine (R01-R03) has something to catch, and a corrected variant to show
a clean pass. Only the branding, manufacturer, and company details differ —
EXAMOX is EXAGON's real label facts (brand/strength/dosage form/excipients/
packaging/stability/storage), not a third party's.
"""

from __future__ import annotations

from app.models import (
    Project,
    Product,
    Manufacturer,
    ActiveIngredient,
    Excipient,
    Packaging,
    StabilityStudy,
    ClinicalEntry,
    BatchFormulaLine,
    Section,
    DosageForm,
    RegistrationType,
    Region,
    ExcipientFunction,
    ManufacturerRole,
    CompendialStatus,
    PackagingComponent,
    StabilityStudyType,
    ClinicalKind,
)

# Buggy variant: the same three copy-paste defect classes as LAMOX's real
# dossier (wrong strength, wrong dosage-form word, leftover foreign-product
# reference) — planted here as test fixtures, not real EXAGON errors.
# NUFLOX is invented test data (deliberately not LATRIM, which is LAMOX's).
BUGGY_P1 = """
3.2.P.1 Description and Composition of drug product

Description: White cap / white body hard gelatin capsules printed "EXAMOX"
and "500", containing almost white powder.

Composition: Each capsule contains Amoxicillin Trihydrate BP equivalent to
Amoxicillin 250mg. Excipients: q.s.

Batch Size: 250,000 Tablets.

(cross-reference: see NUFLOX 960 table of contents for layout)
"""

# The corrected version: 500 mg, capsules, no foreign product reference.
CORRECTED_P1 = """
3.2.P.1 Description and Composition of drug product

Description: White cap / white body hard gelatin capsules printed "EXAMOX"
and "500", containing almost white powder.

Composition: Each capsule contains Amoxicillin Trihydrate BP equivalent to
Amoxicillin 500mg. Excipients: q.s.

Batch Size: 250,000 capsules.
"""


def build_examox(buggy: bool = True) -> Project:
    product = Product(
        brand_name="EXAMOX",
        generic_name="Amoxicillin",
        strength_value=500,
        strength_unit="mg",
        dosage_form=DosageForm.CAPSULE_HARD,
        shelf_life_months=24,
        storage_condition="Store below 30 C. Protect from light.",
        registration_type=RegistrationType.RENEWAL,
        country="Nigeria",
    )
    project = Project(name="EXAMOX renewal", region=Region.NAFDAC, product=product)

    product.manufacturers.append(
        Manufacturer(
            name="Exagon",
            role=ManufacturerRole.FINISHED_PRODUCT,
            site_address="Cadastral Zone, Gwagwalada, Abuja",
            country="Nigeria",
        )
    )
    product.apis.append(
        ActiveIngredient(
            inn_name="Amoxicillin",
            salt_form="Amoxicillin Trihydrate",
            salt_factor=1.148,  # trihydrate/base mass ratio
            compendial_std=CompendialStatus.BP,
        )
    )
    product.excipients.extend(
        [
            Excipient(
                name="Starch",
                function=ExcipientFunction.DILUENT,
                grade="BP",
                compendial_status=CompendialStatus.BP,
            ),
            Excipient(
                name="Magnesium Stearate",
                function=ExcipientFunction.LUBRICANT,
                grade="BP",
                compendial_status=CompendialStatus.BP,
            ),
            Excipient(
                name="Gelatin capsule shell",
                function=ExcipientFunction.CAPSULE_SHELL,
                grade="BP",
                compendial_status=CompendialStatus.BP,
            ),
        ]
    )
    product.packaging.extend(
        [
            Packaging(
                component=PackagingComponent.PRIMARY,
                description="Aluminium foil + PVC blister",
            ),
            Packaging(
                component=PackagingComponent.SECONDARY,
                description="Printed carton with leaflet",
            ),
        ]
    )
    product.stability.append(
        StabilityStudy(
            study_type=StabilityStudyType.LONG_TERM,
            condition="30C/65%RH",
            duration_months=24,
            result_summary="Within specification through 24 months.",
        )
    )
    product.clinical.append(
        ClinicalEntry(
            kind=ClinicalKind.BIOEQUIVALENCE,
            reference_product="Reference amoxicillin 500 mg capsule",
            summary="Comparative BA/BE study; bioequivalence demonstrated.",
        )
    )
    product.batch_formula.append(
        BatchFormulaLine(
            component="Amoxicillin Trihydrate BP (equiv. to Amoxicillin 500 mg)",
            is_active=True,
            spec="BP",
            qty_per_unit_mg=500.0,
            batch_size_units=250_000,
            declared_batch_qty_kg=144.0,
        )
    )

    p1_text = BUGGY_P1 if buggy else CORRECTED_P1
    project.sections.append(
        Section(
            number="3.2.P.1",
            title="Description & Composition",
            narrative_text=p1_text,
        )
    )
    # a second section representing the leftover TOC file reference
    if buggy:
        project.sections.append(
            Section(
                number="1.1",
                title="Table of Contents",
                narrative_text="Table of content (Modules 1-5). NUFLOX 960 layout reused.",
            )
        )
    return project
