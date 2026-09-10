"""AMLOVEX — Amlodipine 5 mg tablets: the end-to-end worked example (P24e).

## Why this fixture exists

`docs/target-toc.yaml` — the contract that decides what a finished dossier
IS — was derived leaf by leaf from a real filed NAFDAC dossier for
amlodipine 5 mg tablets. Everything since P16 has been measured against
that contract, and the closing task of P24 is to show that the platform can
actually produce the dossier the contract describes: seed the product, fill
every collection, attach every uploaded document, build, and count the
leaves.

So this is not another demonstration fixture. **It is the proof.** LAMOX
and EXAMOX carry planted defects for the rule engine to catch; AMPICLOX
carries two actives so repetition has something to repeat over. This one
carries nothing planted at all — it is what a complete, clean filing looks
like, which is the only fixture that can answer "does 98/98 mean anything?"

## Whose product this is

EXAGON's, like EXAMOX. The target TOC was DERIVED from another company's
filed dossier — the structure of a dossier is not anyone's property, and a
leaf list is not confidential — but the product data here is this project's
own fictional company's, not theirs. Copying a third party's specification,
batch numbers and stability results into a repository would be a different
thing entirely, and not a defensible one.

## What is deliberately different from the other seeds

A dihydropyridine rather than a beta-lactam, and that difference is
load-bearing in three places:

  * `amlodipine_substance_specification` — NMT 0.5 % water, not 14.5 %.
    Amoxicillin trihydrate carries three waters by design; amlodipine
    besilate carries almost none.
  * `AMLODIPINE_SUBSTANCE_LONG_TERM` — the timepoint values that go with
    that limit. Reusing the shared table put every timepoint twenty-five
    times over its own limit, and the platform caught it: R23 blocked the
    export and R05 refused the retest period.
  * `DIHYDROPYRIDINE` clinical particulars — an amlodipine SmPC warning a
    patient about penicillin allergy would have undermined the whole
    demonstration on the first page a pharmacist read.

The one chemical fact worth following through the dossier: amlodipine's
characteristic degradation is oxidation of the 1,4-dihydropyridine ring to
the pyridine analogue, and light accelerates it. That is why the impurity
profile names it (3.2.S.3.2), why the pack is an opaque blister
(3.2.P.2.4 / 3.2.P.7), and why the storage statement says to protect it
from light (the label, 1.3.2). One molecule's instability, showing up in
three sections that a filer would otherwise have to keep in step by hand.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.models import (
    ActiveIngredient,
    Applicant,
    BatchFormulaLine,
    Certificate,
    CertificateType,
    ClinicalEntry,
    ClinicalKind,
    CompendialStatus,
    Declaration,
    DeclarationType,
    DosageForm,
    Excipient,
    ExcipientFunction,
    ExcipientOrigin,
    GMPStatus,
    Manufacturer,
    ManufacturerRole,
    Packaging,
    PackagingComponent,
    PackagingRole,
    Product,
    Project,
    RegistrationType,
    Region,
    Section,
)
from app.seed import attach_owner, same_owner_as
from app.seed.bioequivalence import attach_bioequivalence_data
from app.seed.product_information import DIHYDROPYRIDINE, attach_product_information
from app.seed.specifications import (
    amlodipine_impurities,
    amlodipine_substance_specification,
    attach_control_data,
)
from app.seed.stability import AMLODIPINE_SUBSTANCE_LONG_TERM, attach_stability_data

# Amlodipine besilate / amlodipine base, by molecular weight: 567.05 / 408.88.
# The formula weighs the SALT; the label claims the BASE. Rule R04 reconciles
# the two, which is the only reason this number has to be right.
AMLODIPINE_SALT_FACTOR = 1.3868

# The 1,4-dihydropyridine, as base. Public chemistry, and the salt actually
# weighed is the besilate (see the salt factor above) -- the same
# base-not-salt choice EXAMOX documents for amoxicillin trihydrate.
AMLODIPINE_SMILES = "CCOC(=O)C1=C(COCCN)NC(C)=C(C(=O)OC)C1c1ccccc1Cl"

# The 3.2.P.1 narrative. No planted defects -- see the module docstring on
# why this fixture carries none.
CORRECTED_P1 = """
3.2.P.1 Description and Composition of drug product

Description: White to off-white, round, flat-faced bevelled-edge uncoated
tablets, plain on both faces.

Composition: Each tablet contains Amlodipine Besilate BP equivalent to
Amlodipine 5 mg. Excipients: microcrystalline cellulose, anhydrous dibasic
calcium phosphate, sodium starch glycolate and magnesium stearate.

Batch Size: 100,000 tablets.
"""


def build_amlodipine(owner_id: uuid.UUID | None = None) -> Project:
    """A complete, defect-free NAFDAC filing for amlodipine 5 mg tablets."""
    product = Product(
        brand_name="AMLOVEX",
        generic_name="Amlodipine",
        dosage_form=DosageForm.TABLET,
        shelf_life_months=24,
        # Says "protect from light" because the pyridine analogue forms
        # under it -- see this module's docstring. Rule R29 checks this
        # against the temperature the long-term study actually ran at.
        storage_condition="Store below 30 C. Protect from light and moisture.",
        registration_type=RegistrationType.NEW,
        country="Nigeria",
        pack_size="3 x 10 tablets",
        route_of_administration="Oral",
    )
    attach_owner(product, owner_id)
    project = Project(
        name="AMLOVEX 5 mg — new registration",
        region=Region.NAFDAC,
        product=product,
    )

    # Every conditional the target declares, answered. A COMPLETE dossier
    # has answered them (rule R19 warns about silence), and a fixture whose
    # job is to demonstrate completeness must not be mid-question.
    #
    # The two that are TRUE are the point of using a new registration
    # rather than a renewal: 1.2.15 and 1.2.16 mean this filing claims a
    # CEP and an APIMF for its drug substance, which turns 3.2.S.2.2-.2.6
    # from full process descriptions into cross-references. That branch of
    # `development._api_coverage` is otherwise never exercised by a
    # fixture.
    project.condition_answers = {
        "1.2.13": False,
        "1.2.15": True,
        "1.2.16": True,
        "1.2.17": False,
        "1.2.18": False,
        "3.2.P.4.3": False,
        "3.2.P.4.6": False,
        "3.2.A": False,
        "5.3.1.1": False,
        "5.3.1.3": False,
    }

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
                signed_date=date(2026, 2, 2),
                notarized=True,
                notarization_date=date(2026, 2, 4),
            ),
            Declaration(
                declaration_type=DeclarationType.DECLARATION_OF_AUTHENTICITY,
                signed=True,
                signed_date=date(2026, 2, 2),
            ),
            Declaration(
                declaration_type=DeclarationType.GMP_COMPLIANCE_UNDERTAKING,
                signed=True,
                signed_date=date(2026, 2, 2),
                # Notarized, because rule R15 warns on a signed-but-not-
                # notarized declaration and this fixture is meant to be
                # clean. A NAFDAC filing's declarations are notarized or
                # legalized in practice.
                notarized=True,
                notarization_date=date(2026, 2, 4),
            ),
        ]
    )

    api_manufacturer = Manufacturer(
        name="Vardhman Fine Chemicals Ltd",
        role=ManufacturerRole.API_MANUFACTURER,
        site_address="Plot 22, MIDC Industrial Area, Tarapur, Maharashtra",
        country="India",
        gmp_status=GMPStatus.CERTIFIED,
        who_gmp=True,
        manufacturing_licence="MH/API/2019/2244",
    )
    finished_site = Manufacturer(
        name="Exagon",
        role=ManufacturerRole.FINISHED_PRODUCT,
        site_address="Cadastral Zone, Gwagwalada, Abuja",
        country="Nigeria",
        gmp_status=GMPStatus.CERTIFIED,
        manufacturing_licence="NAFDAC/GMP/2025/0114",
    )
    # A packer distinct from the maker, which 3.2.P.3.1 repeats over and
    # 1.2.14's invitation letter has to name. A filing whose sites are one
    # row never exercises either.
    packaging_site = Manufacturer(
        name="Exagon Packaging Services",
        role=ManufacturerRole.PACKAGING_SITE,
        site_address="Plot 19, Idu Industrial Area, Abuja",
        country="Nigeria",
        gmp_status=GMPStatus.CERTIFIED,
        manufacturing_licence="NAFDAC/GMP/2025/0119",
    )
    product.manufacturers.extend([api_manufacturer, finished_site, packaging_site])

    amlodipine = ActiveIngredient(
        inn_name="Amlodipine",
        strength_value=5,
        strength_unit="mg",
        salt_form="Amlodipine Besilate",
        salt_factor=AMLODIPINE_SALT_FACTOR,
        compendial_std=CompendialStatus.BP,
        manufacturer=api_manufacturer,
        # The CEP and APIMF this filing claims. `development._api_coverage`
        # reads exactly these two fields to decide whether 3.2.S.2.2-.2.6
        # are the applicant's to write or a cross-reference to a restricted
        # part -- which is a regulatory decision, made from data, in the
        # rendered document.
        cep_number="CEP 2018-142-Rev 01",
        dmf_number="APIMF/AML/2021/0087",
        specification=amlodipine_substance_specification(),
        impurities=amlodipine_impurities(),
        particle_size="D90 NMT 50 micrometres (laser diffraction)",
        residual_solvents="Methanol, controlled at the ICH Q3C Class 2 limit.",
        smiles=AMLODIPINE_SMILES,
    )
    product.apis.append(amlodipine)

    # A direct-compression tablet formulation. None of these is of human or
    # animal origin, so 3.2.P.4.5 renders the blanket statement -- the
    # opposite branch from EXAMOX's gelatin capsule shell, and the reason
    # rule R21 has both cases covered by a fixture.
    product.excipients.extend(
        [
            Excipient(
                name="Microcrystalline Cellulose",
                function=ExcipientFunction.DILUENT,
                grade="BP",
                compendial_status=CompendialStatus.BP,
                origin=ExcipientOrigin.PLANT,
                supplier="FMC BioPolymer",
            ),
            Excipient(
                name="Anhydrous Dibasic Calcium Phosphate",
                function=ExcipientFunction.DILUENT,
                grade="BP",
                compendial_status=CompendialStatus.BP,
                origin=ExcipientOrigin.MINERAL,
                supplier="Innophos",
            ),
            Excipient(
                name="Sodium Starch Glycolate",
                function=ExcipientFunction.DISINTEGRANT,
                grade="BP",
                compendial_status=CompendialStatus.BP,
                origin=ExcipientOrigin.PLANT,
                supplier="DFE Pharma",
            ),
            Excipient(
                name="Magnesium Stearate",
                function=ExcipientFunction.LUBRICANT,
                grade="BP",
                compendial_status=CompendialStatus.BP,
                origin=ExcipientOrigin.PLANT,
                supplier="Peter Greven",
            ),
        ]
    )

    product.packaging.extend(
        [
            # OPAQUE, and the dossier says why: the pyridine analogue forms
            # under light (3.2.S.3.2). An assessor cross-reads the impurity
            # profile, the pack and the storage statement, and here all
            # three come from one fact about the molecule.
            Packaging(
                component=PackagingComponent.PRIMARY,
                description="Opaque PVC/PVdC-aluminium blister, 10 tablets per strip",
                material="PVC/PVdC + aluminium foil",
            ),
            Packaging(
                component=PackagingComponent.SECONDARY,
                description="Printed carton containing 3 blister strips and a leaflet",
                material="Printed carton board",
                artwork_ref="AMLOVEX-5-CTN-Rev03",
            ),
            Packaging(
                role=PackagingRole.DRUG_SUBSTANCE,
                component=PackagingComponent.PRIMARY,
                description="Double LDPE liner in an HDPE-lined fibre drum, 25 kg",
                material="LDPE / fibreboard",
            ),
        ]
    )

    product.certificates.extend(
        [
            Certificate(
                certificate_type=CertificateType.CPP,
                issuing_authority="NAFDAC",
                certificate_number="NAFDAC/CPP/2026/AMLOVEX-001",
                issue_date=date(2026, 1, 15),
                expiry_date=date.today().replace(year=date.today().year + 2),
            ),
            Certificate(
                certificate_type=CertificateType.GMP,
                issuing_authority="NAFDAC",
                certificate_number="NAFDAC/GMP/2025/0114",
                issue_date=date(2025, 6, 1),
                expiry_date=date.today().replace(year=date.today().year + 1),
            ),
            # The CEP the drug substance claims. The certificate row and
            # `ActiveIngredient.cep_number` are two different statements --
            # one is the document filed at 1.2.15, the other is the claim
            # 3.2.S.2.2 rests on -- and a complete filing makes both.
            Certificate(
                certificate_type=CertificateType.CEP,
                issuing_authority="EDQM",
                certificate_number="CEP 2018-142-Rev 01",
                issue_date=date(2024, 3, 18),
                expiry_date=date.today().replace(year=date.today().year + 3),
            ),
            Certificate(
                certificate_type=CertificateType.MANUFACTURING_LICENCE,
                issuing_authority="NAFDAC",
                certificate_number="NAFDAC/ML/2025/0091",
                issue_date=date(2025, 1, 8),
                expiry_date=date.today().replace(year=date.today().year + 1),
            ),
            Certificate(
                certificate_type=CertificateType.TRADEMARK,
                issuing_authority="Trademarks Registry, Abuja",
                certificate_number="NG/TM/2023/114552",
                issue_date=date(2023, 9, 12),
                expiry_date=date.today().replace(year=date.today().year + 5),
            ),
            Certificate(
                certificate_type=CertificateType.INCORPORATION,
                issuing_authority="Corporate Affairs Commission",
                certificate_number="RC-1149020",
                issue_date=date(2015, 4, 2),
                expiry_date=date.today().replace(year=date.today().year + 10),
            ),
            Certificate(
                certificate_type=CertificateType.PHARMACIST_LICENCE,
                issuing_authority="Pharmacy Council of Nigeria",
                certificate_number="PCN/APL/2026/33417",
                issue_date=date(2026, 1, 5),
                expiry_date=date.today().replace(year=date.today().year + 1),
            ),
            Certificate(
                certificate_type=CertificateType.PREMISES_REGISTRATION,
                issuing_authority="Pharmacy Council of Nigeria",
                certificate_number="PCN/PR/2026/00812",
                issue_date=date(2026, 1, 5),
                expiry_date=date.today().replace(year=date.today().year + 1),
            ),
        ]
    )

    # A 100,000-tablet batch. The active line's per-unit quantity is the
    # BASE (5 mg); the declared batch quantity is the SALT weighed, which is
    # base x salt factor x units. Rule R04 redoes that arithmetic:
    #   5 mg x 1.3868 x 100,000 = 0.693 kg
    product.batch_formula.extend(
        [
            BatchFormulaLine(
                component="Amlodipine Besilate BP (equiv. to Amlodipine 5 mg)",
                is_active=True,
                active_ingredient=amlodipine,
                spec="BP",
                qty_per_unit_mg=5.0,
                batch_size_units=100_000,
                declared_batch_qty_kg=0.6934,
            ),
            BatchFormulaLine(
                component="Microcrystalline Cellulose",
                spec="BP",
                qty_per_unit_mg=60.0,
                batch_size_units=100_000,
                declared_batch_qty_kg=6.0,
            ),
            BatchFormulaLine(
                component="Anhydrous Dibasic Calcium Phosphate",
                spec="BP",
                qty_per_unit_mg=25.0,
                batch_size_units=100_000,
                declared_batch_qty_kg=2.5,
            ),
            BatchFormulaLine(
                component="Sodium Starch Glycolate",
                spec="BP",
                qty_per_unit_mg=8.0,
                batch_size_units=100_000,
                declared_batch_qty_kg=0.8,
            ),
            BatchFormulaLine(
                component="Magnesium Stearate",
                spec="BP",
                qty_per_unit_mg=2.0,
                batch_size_units=100_000,
                declared_batch_qty_kg=0.2,
            ),
        ]
    )

    # The 3.2.P.1 narrative, correct in all three of the things LAMOX and
    # EXAMOX get wrong on purpose: the right strength, the right dosage-form
    # word, and no leftover reference to another product. Rules R01-R03 read
    # exactly this text, and a fixture meant to demonstrate a clean pass has
    # to give them something to pass on.
    #
    # It also has to exist for a duller reason worth recording: `sections` is
    # a lazy-loaded relationship, and a project committed with an EMPTY one
    # raises MissingGreenlet the moment a rule touches it under the async
    # engine. Every other seed happened to append a Section and never met
    # this; the first that did not, did.
    project.sections.append(
        Section(
            number="3.2.P.1",
            title="Description & Composition",
            narrative_text=CORRECTED_P1,
        )
    )

    product.clinical.append(
        ClinicalEntry(
            kind=ClinicalKind.LITERATURE,
            summary=(
                "Published pharmacokinetic and safety literature for amlodipine, "
                "supporting the single-dose crossover design filed at 5.3.1.2."
            ),
        )
    )

    attach_product_information(
        product,
        particulars=DIHYDROPYRIDINE,
        indications=(
            "Treatment of high blood pressure (hypertension), and treatment of "
            "chronic stable angina and vasospastic (Prinzmetal's) angina. It may be "
            "used on its own or together with other medicines for these conditions."
        ),
        posology=(
            "Adults: the usual starting dose is one 5 mg tablet once a day. Your "
            "doctor may increase this to 10 mg once a day. Elderly patients and "
            "patients with liver problems are usually started at a lower dose and "
            "increased slowly. The tablet is swallowed with water and may be taken "
            "with or without food, at about the same time each day."
        ),
    )

    # The substance batch results, amlodipine's rather than the shared
    # penicillin table's -- see AMLODIPINE_SUBSTANCE_LONG_TERM's note. The
    # defaults report the water of crystallisation of a trihydrate, and
    # rule R22 correctly rejected them against a NMT 0.5 % limit the first
    # time this fixture was built.
    attach_control_data(
        product,
        substance_results={
            "Description": ["Complies"] * 3,
            "Assay (anhydrous basis)": ["99.7 % w/w", "99.5 % w/w", "99.8 % w/w"],
            "Related substances - total": ["0.08 %", "0.11 %", "0.09 %"],
            "Water content": ["0.18 %", "0.21 %", "0.16 %"],
        },
        batch_size="100,000 tablets",
    )
    attach_stability_data(product, substance_long_term=AMLODIPINE_SUBSTANCE_LONG_TERM)
    attach_bioequivalence_data(
        product,
        comparator_name="Norvasc 5 mg tablets",
        comparator_manufacturer="Innovator Pharmaceuticals Ltd",
        analyte="Amlodipine in human plasma",
        study_identifier="AMLOVEX/BE/2025-04",
    )

    return project
