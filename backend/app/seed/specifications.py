"""A plausible BP-style drug-substance specification, shared by the seeds.

WHY the seeds share one builder: EXAMOX, LAMOX and AMPICLOX all used the
same free-text string before this ("Assay 90.0-120.0%, related substances
per BP monograph"), and three hand-written copies of the same table would
drift. The shape is what the fixtures are demonstrating; the numbers are
illustrative.

Every `method` here is a CITATION, never method text. Pharmacopoeial
monographs are copyrighted (AGENTS.md §5): a dossier references "BP
monograph", it does not reproduce it, and the knowledge base never
ingests it.

These values are realistic but invented -- do not treat them as the actual
BP limits for any substance.
"""

from __future__ import annotations

from datetime import date

from app.models import (
    BatchAnalysis,
    BatchAnalysisResult,
    Impurity,
    ImpurityType,
    ManufacturerRole,
    SpecificationTest,
)


def bp_substance_specification(assay_lower: str = "98.0", assay_upper: str = "102.0"):
    """The conventional row order an assessor expects: identity first
    (is it the right substance?), then assay (how much?), then impurities
    and physical attributes."""
    rows = [
        ("Description", "Visual, BP monograph", "White to off-white crystalline powder"),
        ("Identification A", "IR absorption, BP monograph", "Complies with reference spectrum"),
        ("Identification B", "HPLC retention time, BP monograph", "Corresponds to reference"),
        ("Assay (anhydrous basis)", "HPLC, BP monograph", f"{assay_lower} - {assay_upper} % w/w"),
        ("Related substances - any individual", "HPLC, BP monograph", "NMT 1.0 %"),
        ("Related substances - total", "HPLC, BP monograph", "NMT 3.0 %"),
        ("Water content", "Karl Fischer, BP monograph", "NMT 14.5 %"),
        ("Sulphated ash", "BP monograph", "NMT 1.0 %"),
        ("Residual solvents", "GC, ICH Q3C", "Complies with ICH Q3C limits"),
        ("Heavy metals", "BP monograph", "NMT 20 ppm"),
        ("Microbial limits", "BP monograph", "TAMC NMT 10^3 CFU/g"),
    ]
    return [
        SpecificationTest(
            test_name=name,
            method=method,
            acceptance_criterion=criterion,
            sort_order=i,
        )
        for i, (name, method, criterion) in enumerate(rows)
    ]


def amlodipine_substance_specification():
    """Amlodipine besilate, for P24e's worked example (3.2.S.4.1).

    THE TEST NAMES ARE DELIBERATELY THE SAME as
    `bp_substance_specification`'s, and only the methods and criteria
    differ. That is not a shortcut -- it is what a drug substance
    specification looks like: identity, assay, related substances, water,
    ash, solvents, heavy metals and microbial limits are the standard test
    set for any small-molecule API, and what varies between molecules is
    the limit, not the question.

    It also has a practical payoff the fixtures depend on: the batch and
    stability result maps are keyed by test name and RAISE on a name the
    specification does not contain, so a shared vocabulary means one set of
    result tables serves every product.

    WHY a separate function rather than parameters on the BP one: the
    criteria differ in kind, not degree. Amoxicillin trihydrate carries
    about 13 % water by design and amlodipine besilate carries almost none,
    so "NMT 14.5 %" is not a default anybody should inherit -- a worked
    example that shipped it would be filing a specification no analyst
    could have written.
    """
    rows = [
        ("Description", "Visual, BP monograph", "White to off-white crystalline powder"),
        ("Identification A", "IR absorption, BP monograph", "Complies with reference spectrum"),
        ("Identification B", "HPLC retention time, BP monograph", "Corresponds to reference"),
        ("Assay (anhydrous basis)", "HPLC, BP monograph", "98.0 - 102.0 % w/w"),
        # Ph. Eur./BP control the named amlodipine impurities individually
        # at 0.3 % and anything unspecified at the ICH Q3A threshold.
        ("Related substances - any individual", "HPLC, BP monograph", "NMT 0.3 %"),
        ("Related substances - total", "HPLC, BP monograph", "NMT 1.0 %"),
        # The contrast with the penicillin specification, and the reason
        # this function exists.
        ("Water content", "Karl Fischer, BP monograph", "NMT 0.5 %"),
        ("Sulphated ash", "BP monograph", "NMT 0.1 %"),
        ("Residual solvents", "GC, ICH Q3C", "Complies with ICH Q3C limits"),
        ("Heavy metals", "BP monograph", "NMT 20 ppm"),
        ("Microbial limits", "BP monograph", "TAMC NMT 10^3 CFU/g"),
    ]
    return [
        SpecificationTest(
            test_name=name,
            method=method,
            acceptance_criterion=criterion,
            sort_order=i,
        )
        for i, (name, method, criterion) in enumerate(rows)
    ]


def amlodipine_impurities():
    """The impurity profile of amlodipine besilate (3.2.S.3.2).

    The pyridine analogue is the one worth knowing: amlodipine is a
    1,4-dihydropyridine, and its characteristic degradation is oxidation of
    that ring to the aromatic pyridine, which light accelerates. That is
    why the product is packed in an opaque blister and why the label says
    to protect it from light -- one impurity explaining a packaging
    decision and a storage statement, which is exactly the cross-read
    3.2.P.2.4 and the label are for.
    """
    return [
        Impurity(
            name="Impurity D (amlodipine pyridine analogue)",
            impurity_type=ImpurityType.DEGRADATION,
            limit="NMT 0.3 %",
            limit_source="BP monograph",
            origin=(
                "Oxidation of the 1,4-dihydropyridine ring to the pyridine, accelerated "
                "by light."
            ),
        ),
        Impurity(
            name="Impurity A (dehydro amlodipine ester)",
            impurity_type=ImpurityType.PROCESS_RELATED,
            limit="NMT 0.3 %",
            limit_source="BP monograph",
            origin="Ester by-product carried through from the synthesis.",
        ),
        Impurity(
            name="Any other unspecified impurity",
            impurity_type=ImpurityType.DEGRADATION,
            limit="NMT 0.10 %",
            limit_source="ICH Q3A identification threshold",
            origin="Unidentified; controlled at the identification threshold.",
        ),
        Impurity(
            name="Methanol",
            impurity_type=ImpurityType.RESIDUAL_SOLVENT,
            limit="NMT 3000 ppm",
            limit_source="ICH Q3C Class 2 limit",
            origin="Solvent used in the final crystallisation step.",
        ),
    ]


def excipient_specification(compendial: str = "BP"):
    """A short compendial excipient specification (3.2.P.4.1).

    Deliberately SHORTER than the drug substance's. That is not laziness --
    it is what an excipient specification looks like. A compendial excipient
    is controlled to its monograph plus the attributes that matter for this
    formulation (particle size for a diluent, for instance); the applicant
    does not re-derive the monograph's full test list into the dossier.
    """
    rows = [
        ("Description", f"Visual, {compendial} monograph", "Complies with monograph"),
        ("Identification", f"{compendial} monograph", "Complies"),
        ("Loss on drying", f"{compendial} monograph", "NMT 15.0 %"),
        ("Microbial limits", f"{compendial} monograph", "TAMC NMT 10^3 CFU/g"),
    ]
    return [
        SpecificationTest(
            test_name=name,
            method=method,
            acceptance_criterion=criterion,
            sort_order=i,
        )
        for i, (name, method, criterion) in enumerate(rows)
    ]


def drug_product_specification(assay_lower: str = "90.0", assay_upper: str = "110.0"):
    """The FINISHED PRODUCT's specification (3.2.P.5.1).

    WHY the assay window is wider than the drug substance's (98.0-102.0):
    this is the real regulatory shape, not an arbitrary difference in the
    fixture. A drug substance is a purified material held to a narrow
    window; a finished dosage form has to absorb content uniformity,
    manufacturing loss and shelf-life degradation on top of it, which is
    why pharmacopoeial finished-product monographs typically allow
    90-110 % of label claim. A platform that stored one specification for
    "the product" would have had to pick one of these two windows and be
    wrong about the other -- which is the concrete reason the owner had to
    become polymorphic rather than the table being reused.

    It also carries the two tests that only a finished product has --
    dissolution and uniformity of dosage units -- which is the other half
    of the same point.
    """
    rows = [
        ("Description", "Visual", "As described in 3.2.P.1"),
        ("Identification", "HPLC, BP monograph", "Retention time corresponds to reference"),
        ("Assay", "HPLC, BP monograph", f"{assay_lower} - {assay_upper} % of label claim"),
        ("Uniformity of dosage units", "BP monograph", "Complies"),
        ("Dissolution", "BP monograph", "NLT 80 % (Q) in 45 minutes"),
        ("Related substances - total", "HPLC, In-house method AM-014", "NMT 5.0 %"),
        ("Water content", "Karl Fischer, BP monograph", "NMT 14.0 %"),
        ("Microbial limits", "BP monograph", "TAMC NMT 10^2 CFU/g"),
    ]
    return [
        SpecificationTest(
            test_name=name,
            method=method,
            acceptance_criterion=criterion,
            sort_order=i,
        )
        for i, (name, method, criterion) in enumerate(rows)
    ]


def batches_against(
    specification,
    batch_numbers,
    results_by_test,
    manufacturer=None,
    batch_size: str = "250,000 capsules",
):
    """Build BatchAnalysis rows whose results point at `specification`'s
    own test objects.

    WHY the seeds go through this helper rather than constructing results
    directly: a result is only meaningful as an answer to a specific test,
    and the link is a foreign key, not a name match. Writing that by hand
    per seed would be three chances to point a result at the wrong test --
    which is exactly the mistake the model shape exists to prevent, so the
    fixtures should not be able to make it either.

    `results_by_test` maps a test name to one reported value per batch.
    A test absent from the map simply is not reported for these batches,
    which is what "Not tested" renders as in 3.2.S.4.4.
    """
    by_name = {test.test_name: test for test in specification}
    unknown = set(results_by_test) - set(by_name)
    if unknown:
        # Loud rather than silent, in the same spirit as folder_for_section:
        # a typo'd test name here would produce a batch table with a row
        # quietly missing, and nobody would notice until an assessor did.
        raise KeyError(
            f"No such test(s) in this specification: {sorted(unknown)}; "
            f"known tests: {sorted(by_name)}"
        )

    batches = []
    for index, number in enumerate(batch_numbers):
        batch = BatchAnalysis(
            batch_number=number,
            manufacture_date=date(2025, 3 + index, 12),
            # P24e: a parameter, because it used to read "capsules" for
            # every fixture and the Amlodipine worked example is a tablet.
            # A batch analysis whose size is stated in the wrong dosage
            # form is the kind of detail an assessor reads as carelessness.
            batch_size=batch_size,
            purpose="Stability and bioequivalence batches",
            manufacturer=manufacturer,
        )
        for test_name, values in results_by_test.items():
            test = by_name[test_name]
            batch.results.append(
                BatchAnalysisResult(
                    specification_test=test,
                    result=values[index],
                    sort_order=test.sort_order,
                )
            )
        batches.append(batch)
    return batches


def penicillin_impurities(inn_name: str):
    """A plausible impurity profile for a penicillin drug substance
    (3.2.S.3.2).

    Realistic in SHAPE, invented in detail -- like every other number in
    these seeds. What the shape demonstrates is the thing the section is
    for: each impurity says where it came from (process or degradation) and
    on whose authority its limit rests. The unnamed-degradant row is
    deliberately the one whose limit is an ICH threshold rather than a
    monograph, because that is the ordinary real case and it is what makes
    rule R11's reminder discriminate rather than fire on everything.
    """
    return [
        Impurity(
            name="Impurity A (6-aminopenicillanic acid)",
            impurity_type=ImpurityType.PROCESS_RELATED,
            limit="NMT 1.0 %",
            limit_source="BP monograph",
            origin="Residual starting material carried through from the synthesis.",
        ),
        Impurity(
            name=f"{inn_name} penilloic acid",
            impurity_type=ImpurityType.DEGRADATION,
            limit="NMT 1.0 %",
            limit_source="BP monograph",
            origin="Hydrolysis of the beta-lactam ring on exposure to moisture.",
        ),
        Impurity(
            name="Any other unspecified impurity",
            impurity_type=ImpurityType.DEGRADATION,
            limit="NMT 0.10 %",
            limit_source="ICH Q3A identification threshold",
            origin="Unidentified; controlled at the qualification threshold.",
        ),
        Impurity(
            name="Dichloromethane",
            impurity_type=ImpurityType.RESIDUAL_SOLVENT,
            limit="NMT 600 ppm",
            limit_source="ICH Q3C Class 2 limit",
            origin="Solvent used in the final crystallisation step.",
        ),
    ]


def drug_product_impurities():
    """3.2.P.5.5 -- the finished product's impurity profile.

    Shorter than the substance's, and degradation-only, which is the
    regulatory point of the section: formulating and packing a medicine
    cannot introduce a process impurity of the API, but it can let the API
    break down. What 3.2.P.5.5 characterises is what the formulation, the
    container and the shelf life allow to form.
    """
    return [
        Impurity(
            name="Total degradation products",
            impurity_type=ImpurityType.DEGRADATION,
            limit="NMT 5.0 %",
            limit_source="BP monograph for the finished dosage form",
            origin="Sum of hydrolysis and polymerisation products over shelf life.",
        ),
        Impurity(
            name="Any individual degradation product",
            impurity_type=ImpurityType.DEGRADATION,
            limit="NMT 1.0 %",
            limit_source="ICH Q3B qualification threshold",
            origin="Controlled at the Q3B threshold for the maximum daily dose.",
        ),
    ]


def attach_control_data(
    product,
    oos: bool = False,
    substance_results: dict | None = None,
    batch_size: str = "250,000 capsules",
) -> None:
    """Wire P20's control-section data onto a seeded product.

    Called once per seed, AFTER the actives, excipients and manufacturers
    are on the product, because every part of it points at one of those.

    WHY one shared function rather than three copies in the seed files:
    exactly the reason `bp_substance_specification` was extracted in P13 --
    three hand-written copies of the same table drift, and what the fixtures
    are demonstrating is the SHAPE. It also means the out-of-specification
    case below has one definition, so a test asserting on it cannot be
    passing against a different fixture than it thinks.

    `oos=True` plants a genuine out-of-specification result: batch two's
    assay reads 103.4 % against a 98.0-102.0 % limit. That is a fixture for
    rule R22 in exactly the spirit of LAMOX's planted copy-paste bugs
    (R01-R03) -- a defect the platform must catch, not a real defect in
    anyone's product.

    `substance_results` overrides the drug substance's batch results, and
    P24e's amlodipine needs it for the same reason it needs its own
    stability table: the defaults report ~13 % water, which is amoxicillin
    trihydrate's water of crystallisation and twenty-five times amlodipine
    besilate's own limit. Rule R22 caught it, correctly, on the first build
    of that fixture -- which is the rule doing exactly its job on the
    fixture written to demonstrate it.

    `batch_size` likewise: it read "250,000 capsules" for every fixture
    until a tablet product needed one.
    """
    finished_site = next(
        (m for m in product.manufacturers if m.role is not ManufacturerRole.API_MANUFACTURER),
        None,
    )
    api_site = next(
        (m for m in product.manufacturers if m.role is ManufacturerRole.API_MANUFACTURER),
        None,
    )

    # 3.2.P.4.1 -- one specification per excipient, the section the whole
    # polymorphic-owner migration was for.
    for excipient in product.excipients:
        if not excipient.specification:
            standard = excipient.compendial_status.value if excipient.compendial_status else "BP"
            excipient.specification = excipient_specification(standard.upper())

    # 3.2.P.5.1 / 3.2.P.5.5 -- the finished product's own control data.
    if not product.specification:
        product.specification = drug_product_specification()
    if not product.impurities:
        product.impurities = drug_product_impurities()

    # 3.2.S.4.4 -- batches of each drug substance, checked against that
    # substance's own specification.
    for index, api in enumerate(product.apis):
        if api.batch_analyses:
            continue
        assays = ["99.1 % w/w", "103.4 % w/w" if oos else "99.8 % w/w", "100.2 % w/w"]
        results = substance_results or {
            "Description": ["Complies"] * 3,
            "Assay (anhydrous basis)": assays,
            "Related substances - total": ["0.42 %", "0.51 %", "0.38 %"],
            "Water content": ["12.8 %", "13.1 %", "12.4 %"],
        }
        api.batch_analyses = batches_against(
            api.specification,
            [
                f"API/{api.inn_name[:3].upper()}/24/{n:04d}"
                for n in (11 + index, 21 + index, 31 + index)
            ],
            results,
            manufacturer=api_site,
            batch_size=batch_size,
        )

    # 3.2.P.5.4 -- batches of the finished product.
    if not product.batch_analyses:
        product.batch_analyses = batches_against(
            product.specification,
            [f"{product.brand_name[:3].upper()}/24/{n:04d}" for n in (101, 102, 103)],
            {
                "Assay": [
                    "98.6 % of label claim",
                    "99.4 % of label claim",
                    "97.9 % of label claim",
                ],
                "Dissolution": ["94 % in 45 min", "92 % in 45 min", "96 % in 45 min"],
                "Uniformity of dosage units": ["Complies"] * 3,
                "Related substances - total": ["0.8 %", "1.1 %", "0.9 %"],
            },
            manufacturer=finished_site,
            batch_size=batch_size,
        )
