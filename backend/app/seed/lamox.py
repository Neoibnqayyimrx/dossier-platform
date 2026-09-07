"""Seed the LAMOX project from the real dossier.

Two variants of the 3.2.P.1 narrative are provided:
- BUGGY: mirrors the real dossier (has the 250mg typo, 'Tablets', and a
  leftover 'LATRIM' reference) so the rule engine has real bugs to catch.
- CORRECTED: the fixed version, so we can show a clean pass.

Everything else reflects LAMOX's actual, non-confidential label facts.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.seed import attach_owner, same_owner_as
from app.models import (
    Project,
    Product,
    Manufacturer,
    ActiveIngredient,
    Excipient,
    Packaging,
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
    ExcipientOrigin,
    ManufacturerRole,
    CompendialStatus,
    CertificateType,
    DeclarationType,
    GMPStatus,
    PackagingComponent,
    PackagingRole,
    ClinicalKind,
)
from app.seed.stability import attach_stability_data
from app.seed.specifications import (
    attach_control_data,
    bp_substance_specification,
    penicillin_impurities,
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


def build_lamox(buggy: bool = True, owner_id: uuid.UUID | None = None) -> Project:
    product = Product(
        brand_name="LAMOX",
        generic_name="Amoxicillin",
        dosage_form=DosageForm.CAPSULE_HARD,
        shelf_life_months=24,
        storage_condition="Store below 30 C. Protect from direct sunlight.",
        registration_type=RegistrationType.RENEWAL,
        country="Nigeria",
    )
    attach_owner(product, owner_id)
    project = Project(name="LAMOX renewal", region=Region.NAFDAC, product=product)
    # P17: the scoping questions this filing answers. A conventional generic
    # claims none of them -- no prior marketing authorization, no CEP or
    # APIMF for the drug substance, no biowaiver in place of an in vivo
    # study, no in-house excipient methods, no novel excipient, no
    # appendices, no BA-only study, no IVIVC. Recorded rather than left
    # blank because a COMPLETE dossier has answered them: rule R19 warns
    # about silence precisely because an unanswered biowaiver question is
    # how a claim goes missing, and a fixture that models a finished filing
    # should not be permanently mid-question.
    project.condition_answers = {
        "1.2.13": False,
        "1.2.15": False,
        "1.2.16": False,
        "1.2.17": False,
        "1.2.18": False,
        "3.2.P.4.3": False,
        "3.2.P.4.6": False,
        "3.2.A": False,
        "5.3.1.1": False,
        "5.3.1.3": False,
    }

    # Module 1 (P08): same treatment as EXAMOX -- present regardless of the
    # buggy/corrected narrative variant, since these are unrelated
    # completeness facts about the real filing.
    project.applicant = Applicant(
        **same_owner_as(product),
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

    # The DRUG SUBSTANCE maker, distinct from the finished-product site.
    # Required by rule R17: the eCTD DTD declares `manufacturer` on
    # `m3-2-s-drug-substance` as #REQUIRED, so an API with no named maker
    # cannot produce a valid backbone.
    api_manufacturer_row = Manufacturer(
        name="Lamox API Supplier",
        role=ManufacturerRole.API_MANUFACTURER,
        country="Nigeria",
        gmp_status=GMPStatus.CERTIFIED,
    )
    product.manufacturers.extend(
        [
            api_manufacturer_row,
            Manufacturer(
                name="Local Pharma Manufacturing Ltd",
                role=ManufacturerRole.FINISHED_PRODUCT,
                country="Nigeria",
                gmp_status=GMPStatus.CERTIFIED,
            ),
        ]
    )
    amoxicillin = ActiveIngredient(
        inn_name="Amoxicillin",
        strength_value=500,
        strength_unit="mg",
        salt_form="Amoxicillin Trihydrate",
        salt_factor=1.148,  # trihydrate/base mass ratio
        compendial_std=CompendialStatus.BP,
        manufacturer=api_manufacturer_row,
        specification=bp_substance_specification(),
        # P20: 3.2.S.3.2. The profile is per SUBSTANCE, so a combination
        # product carries two -- see app/models/impurity.py.
        impurities=penicillin_impurities("Amoxicillin"),
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
                origin=ExcipientOrigin.PLANT,
            ),
            Excipient(
                name="Magnesium Stearate",
                function=ExcipientFunction.LUBRICANT,
                grade="BP",
                compendial_status=CompendialStatus.BP,
                # Vegetable-sourced, and SAID so: magnesium stearate is the
                # textbook case where the same excipient name covers both a
                # plant and an animal material, which is why P19 put origin
                # on the row rather than inferring it from the name.
                origin=ExcipientOrigin.PLANT,
            ),
            Excipient(
                name="Gelatin capsule shell",
                function=ExcipientFunction.CAPSULE_SHELL,
                grade="BP",
                compendial_status=CompendialStatus.BP,
                # Bovine/porcine gelatin -- an excipient of animal origin,
                # so this fixture owes a TSE/BSE certificate (rule R21) and
                # its 3.2.P.4.5 statement is the "these are, and here is the
                # evidence" variant rather than the blanket one.
                origin=ExcipientOrigin.ANIMAL,
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
            # P19: how the API is shipped and stored, which is 3.2.S.6 and
            # is NOT the finished product's packaging. Before the role
            # existed, one of these two sections had to be answered with the
            # other's data.
            Packaging(
                role=PackagingRole.DRUG_SUBSTANCE,
                component=PackagingComponent.PRIMARY,
                description="Double LDPE liner in an HDPE-lined fibre drum",
                material="LDPE / fibreboard",
            ),
        ]
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
    # P19: the supplier's evidence for the gelatin capsule shell. Rule R21
    # makes an animal-origin excipient with no such certificate an ERROR --
    # this fixture files a complete dossier, so it has one.
    product.certificates.append(
        Certificate(
            certificate_type=CertificateType.TSE_BSE,
            issuing_authority="Capsule shell supplier",
            certificate_number="TSE/LAMOX/2026-001",
            issue_date=date(2026, 1, 10),
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
    # P20: the control sections' data -- excipient and drug-product
    # specifications, impurity profiles, and batch analyses checked against
    # each owner's own specification. Attached last because every part of it
    # points at an active, an excipient or a manufacturing site.
    attach_control_data(product)
    # P21: the timepoint tables 3.2.S.7.3 and 3.2.P.8.3 ARE, plus the
    # studies' real axes -- one per batch, in the marketed pack. Must run
    # after attach_control_data: every study names a batch and every
    # result names a specification test, and that function creates both.
    attach_stability_data(product)

    return project
