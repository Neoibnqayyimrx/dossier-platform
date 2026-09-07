"""The bioequivalence study every seeded filing owes (P22).

Called AFTER `attach_control_data`, for the same reason
`attach_stability_data` is: the study points at the batch whose analysis
3.2.P.5.4 files, and that function is what creates it. A string here would
let the BE study and the batch table name different material -- which is
the drift the foreign key exists to prevent, so the fixtures must not be
able to introduce it either.

## Why the seeds needed this the moment rule R06 was rewritten

Every seed models a COMPLETE filing -- that is what makes them useful for
testing assembly, the CTD build and the eCTD backbone. R06 used to be
satisfied by a `ClinicalEntry` row saying "bioequivalence demonstrated".
It is not any more, and rightly: a multisource filing whose central
document is a sentence is not a complete filing. Attaching a real study is
the fix; teaching the tests to override R06 would be the same fixture with
the new rule switched off.

Every number below is realistic in SHAPE and invented in detail, exactly
like the specification and stability values beside it. Do not read them as
anyone's real bioequivalence data.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models import (
    BEDoseRegimen,
    BEFedState,
    BEStudyDesign,
    BioequivalenceResult,
    BioequivalenceStudy,
    PKParameter,
    ReferenceProduct,
)

# A passing study, stated as the ratio and the two bounds the CRO's
# statistician reports. Comfortably inside 80.00-125.00 % without sitting
# on the boundary -- a fixture that passes by 0.01 % is a fixture that
# starts failing the day someone changes a rounding rule.
PASSING_INTERVALS: dict[PKParameter, tuple[str, str, str, str]] = {
    # parameter: (geometric mean ratio, CI lower, CI upper, intra-subject CV)
    PKParameter.CMAX: ("98.42", "91.30", "106.10", "18.40"),
    PKParameter.AUC_0_T: ("101.15", "95.80", "106.80", "12.10"),
    PKParameter.AUC_0_INF: ("100.90", "95.40", "106.70", "12.30"),
}

# The planted defect, in the spirit of LAMOX's copy-paste bugs: Cmax's
# lower bound falls below 80.00 %, so bioequivalence is NOT demonstrated
# and rule R25 must block the export naming Cmax and the lower bound.
#
# WHY Cmax and not AUC: it is the realistic one. Cmax is the noisier
# parameter, and a generic that dissolves slightly slower than the
# innovator fails on rate long before it fails on extent.
FAILING_INTERVALS: dict[PKParameter, tuple[str, str, str, str]] = {
    PKParameter.CMAX: ("86.10", "76.40", "97.00", "31.20"),
    PKParameter.AUC_0_T: ("101.15", "95.80", "106.80", "12.10"),
    PKParameter.AUC_0_INF: ("100.90", "95.40", "106.70", "12.30"),
}

_PARAMETER_ORDER = {parameter: index for index, parameter in enumerate(PKParameter)}


def intervals(values: dict[PKParameter, tuple[str, str, str, str]]) -> list[BioequivalenceResult]:
    """Build the three result rows, in the order every report prints them."""
    return [
        BioequivalenceResult(
            parameter=parameter,
            geometric_mean_ratio=Decimal(ratio),
            ci_lower=Decimal(lower),
            ci_upper=Decimal(upper),
            intra_subject_cv=Decimal(cv),
            sort_order=_PARAMETER_ORDER[parameter],
        )
        for parameter, (ratio, lower, upper, cv) in values.items()
    ]


def attach_bioequivalence_data(
    product,
    *,
    comparator_name: str,
    comparator_manufacturer: str = "Innovator Pharmaceuticals Ltd",
    analyte: str,
    study_identifier: str,
    failing: bool = False,
    comparator_mismatch: bool = False,
) -> None:
    """Wire a complete bioequivalence study onto a seeded product.

    `failing` plants an out-of-window Cmax interval; `comparator_mismatch`
    plants a study run against a comparator the application does not
    declare. Both are fixtures for a rule, in the same spirit as
    `attach_stability_data(oos=True)` -- defects the platform must catch,
    not defects in anyone's product.
    """
    if product.bioequivalence_studies:
        # Already seeded. Never top up: a second study on the same batch
        # would put two rows in 5.2 for one piece of work.
        return

    # What the APPLICATION declares -- printed at 1.2 and 2.3.
    product.reference_product_name = comparator_name
    product.reference_product_manufacturer = comparator_manufacturer

    # What the STUDY dosed. Normally the same product; with
    # `comparator_mismatch` a different brand entirely, which is the real
    # filing error rule R26 exists to catch: the comparator originally
    # planned is not the one the CRO could source, the study runs against
    # what was bought, and Module 1 still names the original.
    reference = ReferenceProduct(
        name="Ospamox 500 mg capsules" if comparator_mismatch else comparator_name,
        strength=product.strength_display or None,
        dosage_form=product.dosage_form.value if product.dosage_form else None,
        manufacturer=comparator_manufacturer,
        country_of_origin="United Kingdom",
        batch_number="REF/24/1180",
        # In date at the time of dosing, which is what an assessor checks
        # the study period against.
        expiry_date=date(2027, 8, 31),
        purchase_country="United Kingdom",
    )
    product.reference_products.append(reference)

    # The biobatch is one of the batches 3.2.P.5.4 already files, and its
    # size clears the WHO TRS 992 threshold that rule R27 applies: the
    # commercial batch in this fixture's 3.2.P.3.2 is 250 000 units, so a
    # tenth of it is 25 000 -- and the 100 000-unit floor is the binding
    # figure. 120 000 clears it.
    test_batch = product.batch_analyses[0] if product.batch_analyses else None

    study = BioequivalenceStudy(
        study_identifier=study_identifier,
        title=(
            f"An open-label, randomised, two-treatment, two-period, two-sequence "
            f"crossover bioequivalence study of {product.brand_name} against "
            f"{comparator_name} in healthy adult volunteers under fasting conditions"
        ),
        design=BEStudyDesign.CROSSOVER,
        fed_state=BEFedState.FASTING,
        dose_regimen=BEDoseRegimen.SINGLE_DOSE,
        subjects_enrolled=36,
        subjects_completed=34,
        analyte=analyte,
        bioanalytical_method=(
            "Validated LC-MS/MS in human plasma; method validation report filed at 5.3.1.4"
        ),
        cro_name="Accord Clinical Research Ltd",
        study_site="Clinical Pharmacology Unit, Lagos",
        start_date=date(2025, 6, 3),
        completion_date=date(2025, 8, 19),
        reference_product=reference,
        test_batch=test_batch,
        test_batch_size_units=120_000,
        test_batch_manufacture_date=date(2025, 3, 12),
    )
    study.results.extend(intervals(FAILING_INTERVALS if failing else PASSING_INTERVALS))
    product.bioequivalence_studies.append(study)
