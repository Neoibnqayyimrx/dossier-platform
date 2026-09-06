"""Seed AMPICLOX — a fixed-dose combination product (ampicillin +
cloxacillin), demonstrating that the data model supports more than one
active ingredient per product.

This exists to answer a concrete question: everything built through P05
(EXAMOX, LAMOX) was single-API, even though Product.apis was already a
list. Strength lived on Product (one value), which had nowhere to put a
second active's strength -- exactly the gap a real combination product
(this one, or artemether-lumefantrine) would have hit. Strength moved to
ActiveIngredient to fix that; this fixture is the proof.

Two narrative variants, same idea as LAMOX/EXAMOX's buggy/corrected pair,
but the defect here is specifically on the SECOND active ingredient
(Cloxacillin) -- proving the rewritten R01 rule checks every API's
strength independently, not just the first one (`apis[0]`), which is
exactly the bug this fixture was built to catch.
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
    StabilityStudy,
    ClinicalEntry,
    BatchFormulaLine,
    Section,
    Applicant,
    Certificate,
    Declaration,
    DosageForm,
    RegistrationType,
    Region,
    ExcipientFunction,
    ExcipientOrigin,
    ManufacturerRole,
    CompendialStatus,
    PackagingComponent,
    PackagingRole,
    StabilityStudyType,
    ClinicalKind,
    CertificateType,
    DeclarationType,
    GMPStatus,
)
from app.seed.specifications import (
    attach_control_data,
    bp_substance_specification,
    penicillin_impurities,
)

# The defect is only on Cloxacillin's strength (125mg instead of 250mg) --
# a mismatch the old, single-API-assuming R01 could never have caught,
# since it only ever looked at product.strength_value / apis[0].
BUGGY_P1 = """
3.2.P.1 Description and Composition of drug product

Description: White cap / white body hard gelatin capsules printed
"AMPICLOX", containing white to off-white powder.

Composition: Each capsule contains Ampicillin Trihydrate BP equivalent to
Ampicillin 250mg and Cloxacillin Sodium BP equivalent to Cloxacillin 125mg.
Excipients: q.s.

Batch Size: 100,000 capsules.
"""

CORRECTED_P1 = """
3.2.P.1 Description and Composition of drug product

Description: White cap / white body hard gelatin capsules printed
"AMPICLOX", containing white to off-white powder.

Composition: Each capsule contains Ampicillin Trihydrate BP equivalent to
Ampicillin 250mg and Cloxacillin Sodium BP equivalent to Cloxacillin 250mg.
Excipients: q.s.

Batch Size: 100,000 capsules.
"""


def build_ampiclox(buggy: bool = True, owner_id: uuid.UUID | None = None) -> Project:
    product = Product(
        brand_name="AMPICLOX",
        generic_name="Ampicillin + Cloxacillin",
        dosage_form=DosageForm.CAPSULE_HARD,
        shelf_life_months=24,
        storage_condition="Store below 30 C. Protect from light.",
        registration_type=RegistrationType.NEW,
        country="Nigeria",
    )
    attach_owner(product, owner_id)
    project = Project(name="AMPICLOX new registration", region=Region.NAFDAC, product=product)
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

    # Administrative completeness, mirroring EXAMOX. WHY this fixture needs
    # it at all: without an applicant, declarations, a CPP and a GMP status,
    # the P06 completeness rules block assembly, so AMPICLOX could only ever
    # be run through the rule engine -- which meant NO combination product
    # had ever been through P07 assembly or a P08 CTD build. These facts are
    # unrelated to the planted R01 defect and are present in both variants.
    project.applicant = Applicant(
        **same_owner_as(product),
        company_name="Exagon Pharmaceuticals Ltd",
        address="Cadastral Zone, Gwagwalada, Abuja",
        country="Nigeria",
        contact_name="Aisha Bello",
        contact_email="regulatory@exagon.example",
        contact_phone="+234-800-000-0000",
        authorized_representative_name="Aisha Bello",
        authorized_representative_title="Head of Regulatory Affairs",
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
    product.certificates.append(
        Certificate(
            certificate_type=CertificateType.CPP,
            issuing_authority="NAFDAC",
            certificate_number="NAFDAC/CPP/2026/AMPICLOX-001",
            issue_date=date(2026, 1, 15),
            expiry_date=date.today().replace(year=date.today().year + 2),
        )
    )

    # The DRUG SUBSTANCE maker, distinct from the finished-product site.
    # Required by rule R17: the eCTD DTD declares `manufacturer` on
    # `m3-2-s-drug-substance` as #REQUIRED, so an API with no named maker
    # cannot produce a valid backbone.
    api_manufacturer = Manufacturer(
        name="Exagon API Division",
        role=ManufacturerRole.API_MANUFACTURER,
        site_address="Plot 4, Industrial Layout, Ota, Ogun State",
        country="Nigeria",
        gmp_status=GMPStatus.CERTIFIED,
    )
    product.manufacturers.append(api_manufacturer)
    product.manufacturers.append(
        Manufacturer(
            name="Exagon",
            role=ManufacturerRole.FINISHED_PRODUCT,
            site_address="Cadastral Zone, Gwagwalada, Abuja",
            country="Nigeria",
            gmp_status=GMPStatus.CERTIFIED,
        )
    )

    ampicillin = ActiveIngredient(
        inn_name="Ampicillin",
        strength_value=250,
        strength_unit="mg",
        salt_form="Ampicillin Trihydrate",
        salt_factor=1.155,  # trihydrate/anhydrous mass ratio
        compendial_std=CompendialStatus.BP,
        manufacturer=api_manufacturer,
        specification=bp_substance_specification(),
        # P20: 3.2.S.3.2. The profile is per SUBSTANCE, so a combination
        # product carries two -- see app/models/impurity.py.
        impurities=penicillin_impurities("Ampicillin"),
        smiles="CC1(C)S[C@@H]2[C@H](NC(=O)[C@H](N)c3ccccc3)C(=O)N2[C@H]1C(=O)O",
    )
    cloxacillin = ActiveIngredient(
        inn_name="Cloxacillin",
        strength_value=250,
        strength_unit="mg",
        salt_form="Cloxacillin Sodium",
        salt_factor=1.092,  # sodium salt/free-acid mass ratio
        compendial_std=CompendialStatus.BP,
        manufacturer=api_manufacturer,
        specification=bp_substance_specification(),
        # P20: 3.2.S.3.2. The profile is per SUBSTANCE, so a combination
        # product carries two -- see app/models/impurity.py.
        impurities=penicillin_impurities("Cloxacillin"),
        smiles="CC1(C)S[C@@H]2[C@H](NC(=O)c3c(C)onc3-c3ccccc3Cl)C(=O)N2[C@H]1C(=O)O",
    )
    product.apis.extend([ampicillin, cloxacillin])

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
            reference_product="Reference ampicillin/cloxacillin 250mg/250mg capsule",
            summary="Comparative BA/BE study; bioequivalence demonstrated.",
        )
    )
    # Two active batch-formula lines, each linked to ITS OWN API via
    # active_ingredient -- this is the fact R04 needs to reconcile each
    # active's batch quantity against its own salt_factor, not just the
    # first API found on the product.
    # P19: the supplier's evidence for the gelatin capsule shell. Rule R21
    # makes an animal-origin excipient with no such certificate an ERROR --
    # this fixture files a complete dossier, so it has one.
    product.certificates.append(
        Certificate(
            certificate_type=CertificateType.TSE_BSE,
            issuing_authority="Capsule shell supplier",
            certificate_number="TSE/AMPICLOX/2026-001",
            issue_date=date(2026, 1, 10),
            expiry_date=date.today().replace(year=date.today().year + 2),
        )
    )
    product.batch_formula.extend(
        [
            BatchFormulaLine(
                component="Ampicillin Trihydrate BP (equiv. to Ampicillin 250 mg)",
                is_active=True,
                active_ingredient=ampicillin,
                spec="BP",
                qty_per_unit_mg=250.0,
                batch_size_units=100_000,
                declared_batch_qty_kg=28.9,  # 250mg * 1.155 * 100,000 / 1e6
            ),
            BatchFormulaLine(
                component="Cloxacillin Sodium BP (equiv. to Cloxacillin 250 mg)",
                is_active=True,
                active_ingredient=cloxacillin,
                spec="BP",
                qty_per_unit_mg=250.0,
                batch_size_units=100_000,
                declared_batch_qty_kg=27.3,  # 250mg * 1.092 * 100,000 / 1e6
            ),
        ]
    )

    p1_text = BUGGY_P1 if buggy else CORRECTED_P1
    project.sections.append(
        Section(
            number="3.2.P.1",
            title="Description & Composition",
            narrative_text=p1_text,
        )
    )
    # P20: the control sections' data -- excipient and drug-product
    # specifications, impurity profiles, and batch analyses checked against
    # each owner's own specification. Attached last because every part of it
    # points at an active, an excipient or a manufacturing site.
    attach_control_data(product, oos=buggy)

    return project
