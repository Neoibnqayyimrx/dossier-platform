"""Seed the EXAMOX project — our own company's (EXAGON) product.

Same structure as app/seed/lamox.py (see reference/worked-example-lamox.md for
the provenance of that pattern): two variants of the 3.2.P.1 narrative so the
rule engine (R01-R03) has something to catch, and a corrected variant to show
a clean pass. Only the branding, manufacturer, and company details differ —
EXAMOX is EXAGON's real label facts (brand/strength/dosage form/excipients/
packaging/stability/storage), not a third party's.
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
from app.seed.bioequivalence import attach_bioequivalence_data
from app.seed.stability import attach_stability_data
from app.seed.specifications import (
    attach_control_data,
    bp_substance_specification,
    penicillin_impurities,
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


def build_examox(buggy: bool = True, owner_id: uuid.UUID | None = None) -> Project:
    product = Product(
        brand_name="EXAMOX",
        generic_name="Amoxicillin",
        dosage_form=DosageForm.CAPSULE_HARD,
        shelf_life_months=24,
        storage_condition="Store below 30 C. Protect from light.",
        registration_type=RegistrationType.RENEWAL,
        country="Nigeria",
    )
    attach_owner(product, owner_id)
    project = Project(name="EXAMOX renewal", region=Region.NAFDAC, product=product)
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

    # Module 1 (P08): who is filing, and this filing's signed/notarized
    # administrative declarations -- unrelated completeness facts about the
    # real product/filing, present regardless of the buggy/corrected
    # narrative variant, same treatment as the CPP certificate below.
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
    amoxicillin = ActiveIngredient(
        inn_name="Amoxicillin",
        # Strength lives on the API, not the product, so a combination
        # product (see app/seed/ampiclox.py) has somewhere to put a second
        # one. EXAMOX has just the one active.
        strength_value=500,
        strength_unit="mg",
        salt_form="Amoxicillin Trihydrate",
        salt_factor=1.148,  # trihydrate/base mass ratio
        compendial_std=CompendialStatus.BP,
        manufacturer=api_manufacturer,
        specification=bp_substance_specification(),
        # P20: 3.2.S.3.2. The profile is per SUBSTANCE, so a combination
        # product carries two -- see app/models/impurity.py.
        impurities=penicillin_impurities("Amoxicillin"),
        # base (anhydrous) amoxicillin structure -- public chemistry,
        # not the trihydrate salt actually weighed (see salt_factor).
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
    # P22: the bioequivalence STUDY is no longer a ClinicalEntry row --
    # it is structured data attached below by `attach_bioequivalence_data`,
    # because a sentence cannot carry a confidence interval and 1.4.1 is
    # generated entirely from those. What stays here is what this table is
    # genuinely for: the literature the filing relies on (5.4).
    product.clinical.append(
        ClinicalEntry(
            kind=ClinicalKind.LITERATURE,
            summary=(
                "Published pharmacokinetic and safety literature for the active "
                "substance, filed at 5.4."
            ),
        )
    )
    # Required for a NAFDAC filing (rule R13) -- unexpired, on file
    # regardless of the buggy/corrected narrative variant, since this is
    # an unrelated completeness fact about the real product, not one of
    # the planted R01-R03 copy-paste bugs.
    product.certificates.append(
        Certificate(
            certificate_type=CertificateType.CPP,
            issuing_authority="NAFDAC",
            certificate_number="NAFDAC/CPP/2026/EXAMOX-001",
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
            certificate_number="TSE/EXAMOX/2026-001",
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
    # a second section representing the leftover TOC file reference
    if buggy:
        project.sections.append(
            Section(
                number="1.1",
                title="Table of Contents",
                narrative_text="Table of content (Modules 1-5). NUFLOX 960 layout reused.",
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
    # P22: the study that carries the entire scientific argument for a
    # multisource approval. Runs after attach_control_data for the same
    # reason stability does -- the study names the batch 3.2.P.5.4 files,
    # as a foreign key rather than a re-typed batch number.
    attach_bioequivalence_data(
        product,
        comparator_name="Amoxil 500 mg capsules",
        analyte="Amoxicillin in human plasma",
        study_identifier="EXAMOX/BE/2025-01",
    )

    return project
