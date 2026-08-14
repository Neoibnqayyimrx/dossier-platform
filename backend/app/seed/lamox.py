"""Seed the LAMOX project from the real dossier.

Two variants of the 3.2.P.1 narrative are provided:
- BUGGY: mirrors the real dossier (has the 250mg typo, 'Tablets', and a
  leftover 'LATRIM' reference) so the rule engine has real bugs to catch.
- CORRECTED: the fixed version, so we can show a clean pass.

Everything else reflects LAMOX's actual, non-confidential label facts.
"""

from __future__ import annotations

from datetime import date

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
    Certificate,
    Applicant,
    Declaration,
    Section,
    DosageForm,
    RegistrationType,
    Region,
    ExcipientFunction,
    ManufacturerRole,
    CompendialStatus,
    CertificateType,
    DeclarationType,
    GMPStatus,
    PackagingComponent,
    StabilityStudyType,
    ClinicalKind,
)
from app.seed.specifications import bp_substance_specification

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
    product = Product(
        brand_name="LAMOX",
        generic_name="Amoxicillin",
        dosage_form=DosageForm.CAPSULE_HARD,
        shelf_life_months=24,
        storage_condition="Store below 30 C. Protect from direct sunlight.",
        registration_type=RegistrationType.RENEWAL,
        country="Nigeria",
    )
    project = Project(name="LAMOX renewal", region=Region.NAFDAC, product=product)

    # Module 1 (P08): same treatment as EXAMOX -- present regardless of the
    # buggy/corrected narrative variant, since these are unrelated
    # completeness facts about the real filing.
    project.applicant = Applicant(
        company_name="Local Pharma Manufacturing Ltd",
        country="Nigeria",
        contact_name="Chidi Okafor",
        contact_email="regulatory@localpharma.example",
        contact_phone="+234-800-111-1111",
        authorized_representative_name="Chidi Okafor",
        authorized_representative_title="Regulatory Affairs Manager",
    )
    project.declarations.extend(
        [
            Declaration(
                declaration_type=DeclarationType.POWER_OF_ATTORNEY,
                signed=True,
                signed_date=date(2026, 1, 20),
                notarized=True,
                notarization_date=date(2026, 1, 22),
            ),
            Declaration(
                declaration_type=DeclarationType.DECLARATION_OF_AUTHENTICITY,
                signed=True,
                signed_date=date(2026, 1, 20),
            ),
        ]
    )

    product.manufacturers.append(
        Manufacturer(
            name="Local Pharma Manufacturing Ltd",
            role=ManufacturerRole.FINISHED_PRODUCT,
            country="Nigeria",
            gmp_status=GMPStatus.CERTIFIED,
        )
    )
    amoxicillin = ActiveIngredient(
        inn_name="Amoxicillin",
        strength_value=500,
        strength_unit="mg",
        salt_form="Amoxicillin Trihydrate",
        salt_factor=1.148,  # trihydrate/base mass ratio
        compendial_std=CompendialStatus.BP,
        specification=bp_substance_specification(),
        smiles="CC1(C)S[C@@H]2[C@H](NC(=O)[C@H](N)c3ccc(O)cc3)C(=O)N2[C@H]1C(=O)O",
    )
    product.apis.append(amoxicillin)
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
            Packaging(
                component=PackagingComponent.CARTON,
                description="7-ply corrugated shipper",
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
    product.certificates.append(
        Certificate(
            certificate_type=CertificateType.CPP,
            issuing_authority="NAFDAC",
            certificate_number="NAFDAC/CPP/2026/LAMOX-001",
            issue_date=date(2026, 1, 15),
            expiry_date=date.today().replace(year=date.today().year + 2),
        )
    )
    product.batch_formula.append(
        BatchFormulaLine(
            component="Amoxicillin Trihydrate BP (equiv. to Amoxicillin 500 mg)",
            is_active=True,
            active_ingredient=amoxicillin,
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
    # a second section representing the leftover TOC file reference (real)
    if buggy:
        project.sections.append(
            Section(
                number="1.1",
                title="Table of Contents",
                narrative_text="Table of content (Modules 1-5). LATRIM 960 layout reused.",
            )
        )
    return project
