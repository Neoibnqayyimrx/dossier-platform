"""Realistic multi-timepoint stability data for the seeds (P21).

WHY this is its own module rather than three copies in the seed files:
exactly the reason `specifications.py` was extracted -- three
hand-written copies of the same table drift, and what the fixtures are
demonstrating is the SHAPE, not the numbers.

## What the shape is

ICH Q1A(R2), reduced to the parts a data model has to carry:

  * **Long-term data on at least three primary batches.** So the seed
    builds one study per batch, not one study for "the product" -- and
    each one is foreign-keyed to the batch whose analysis 3.2.P.5.4
    already files, so the two sections cannot name different batches.
  * **In the container closure system proposed for marketing.** So each
    study names a pack. A shelf life supported in a drum does not support
    a blister.
  * **Accelerated data alongside it**, at 40 C / 75 % RH for six months.
    It detects significant change; it does not establish the shelf life,
    which is what rule R24 says when it is all that is on file.
  * **The drug substance has its own studies**, supporting a retest
    period rather than a shelf life (3.2.S.7).

Every number here is illustrative -- realistic in direction and
magnitude, invented in detail. The direction is the part that matters:
assay drifts down, degradation products up, and dissolution slows, which
is what makes a timepoint table worth reading at all.
"""

from __future__ import annotations

from app.models import (
    PackagingComponent,
    PackagingRole,
    StabilityResult,
    StabilityStudy,
    StabilityStudyType,
)

# ICH Q1A(R2) 2.1.5: every three months in the first year, every six in
# the second, annually after. Trimmed to the five that show the trend --
# a fixture with twelve columns demonstrates nothing the five do not.
LONG_TERM_TIMEPOINTS = (0, 6, 12, 18, 24)
# Six months at the accelerated condition, tested 0/3/6.
ACCELERATED_TIMEPOINTS = (0, 3, 6)

# test name -> one value per timepoint. Keyed by the SPECIFICATION's own
# test names, and `results_at` raises on a name the specification does not
# contain -- a typo here would silently drop a row from 3.2.P.8.3 and
# nobody would notice until an assessor did.
DRUG_PRODUCT_LONG_TERM = {
    "Description": ("Complies",) * 5,
    "Assay": (
        "99.4 % of label claim",
        "99.0 % of label claim",
        "98.4 % of label claim",
        "97.8 % of label claim",
        "97.1 % of label claim",
    ),
    "Dissolution": (
        "94 % in 45 min",
        "93 % in 45 min",
        "91 % in 45 min",
        "89 % in 45 min",
        "87 % in 45 min",
    ),
    "Related substances - total": ("0.8 %", "1.4 %", "2.1 %", "2.9 %", "3.6 %"),
    "Water content": ("3.1 %", "3.4 %", "3.6 %", "3.9 %", "4.1 %"),
}

DRUG_PRODUCT_ACCELERATED = {
    "Description": ("Complies",) * 3,
    "Assay": (
        "99.4 % of label claim",
        "98.1 % of label claim",
        "96.5 % of label claim",
    ),
    "Dissolution": ("94 % in 45 min", "90 % in 45 min", "86 % in 45 min"),
    "Related substances - total": ("0.8 %", "2.2 %", "3.9 %"),
    "Water content": ("3.1 %", "3.8 %", "4.4 %"),
}

DRUG_SUBSTANCE_LONG_TERM = {
    "Description": ("Complies",) * 5,
    "Assay (anhydrous basis)": (
        "99.8 % w/w",
        "99.6 % w/w",
        "99.3 % w/w",
        "99.0 % w/w",
        "98.6 % w/w",
    ),
    "Related substances - total": ("0.42 %", "0.61 %", "0.88 %", "1.20 %", "1.55 %"),
    "Water content": ("12.8 %", "12.9 %", "13.1 %", "13.2 %", "13.4 %"),
}

# The planted defect, in the same spirit as LAMOX's copy-paste bugs: a
# dossier claiming 24 months whose own table shows dissolution failing at
# 12. NOT a real defect in anyone's product -- a fixture for rule R23.
OUT_OF_SPECIFICATION_DISSOLUTION = (
    "94 % in 45 min",
    "91 % in 45 min",
    "68 % in 45 min",
    "64 % in 45 min",
    "61 % in 45 min",
)


def results_at(specification, timepoints, values_by_test) -> list[StabilityResult]:
    """Build the timepoint results for one study, pointed at
    `specification`'s own test objects.

    The link is a foreign key, not a name match, for the same reason
    `batches_against` takes this shape: a result is only meaningful as an
    answer to a specific test, and writing that by hand per seed would be
    three chances to point a result at the wrong limit -- the exact mistake
    the model exists to prevent, so the fixtures should not be able to make
    it either.
    """
    by_name = {test.test_name: test for test in specification}
    unknown = set(values_by_test) - set(by_name)
    if unknown:
        raise KeyError(
            f"No such test(s) in this specification: {sorted(unknown)}; "
            f"known tests: {sorted(by_name)}"
        )

    results = []
    for test_name, values in values_by_test.items():
        test = by_name[test_name]
        if len(values) != len(timepoints):
            raise ValueError(
                f"{test_name!r} has {len(values)} values for {len(timepoints)} timepoints"
            )
        for months, value in zip(timepoints, values):
            results.append(
                StabilityResult(
                    specification_test=test,
                    timepoint_months=months,
                    result=value,
                    sort_order=test.sort_order,
                )
            )
    return results


def _marketed_pack(product):
    """The primary pack the finished product is sold in.

    The role test is NEGATIVE, matching `instances._drug_product_packs`:
    `Packaging.role` has a Python-side default that SQLAlchemy applies at
    flush, so a pack built in memory still has `role is None`, and asking
    `is DRUG_PRODUCT` here would find nothing at all in a seed.
    """
    return next(
        (
            pack
            for pack in product.packaging
            if pack.role is not PackagingRole.DRUG_SUBSTANCE
            and pack.component is PackagingComponent.PRIMARY
        ),
        None,
    )


def _substance_pack(product, api):
    """How the API is shipped: the drum, not the blister (3.2.S.6). A
    positive test, because claiming a pack is the substance's is a
    statement about a material rather than a default."""
    return next(
        (
            pack
            for pack in product.packaging
            if pack.role is PackagingRole.DRUG_SUBSTANCE
            and (pack.active_ingredient is None or pack.active_ingredient is api)
        ),
        None,
    )


def attach_stability_data(product, oos: bool = False) -> None:
    """Wire P21's stability studies onto a seeded product.

    Called AFTER `attach_control_data`, because every study points at a
    batch and every result points at a specification test -- both of which
    that function creates.

    `oos=True` plants a genuine out-of-specification result: dissolution
    reads 68 % at 12 months against an NLT 80 % limit, on a product
    claiming 24 months. That is a fixture for rule R23 in exactly the
    spirit of LAMOX's planted copy-paste bugs -- a defect the platform must
    catch, not a real defect in anyone's product.
    """
    if product.stability:
        # Already seeded (or hand-built by a caller). Never top up: a
        # second set of studies on the same batches would double every
        # column of 3.2.P.8.3.
        return

    pack = _marketed_pack(product)

    # ---- 3.2.P.8: long-term on every primary batch, in the marketed pack
    for index, batch in enumerate(product.batch_analyses):
        values = dict(DRUG_PRODUCT_LONG_TERM)
        if oos and index == 0:
            values["Dissolution"] = OUT_OF_SPECIFICATION_DISSOLUTION
        study = StabilityStudy(
            study_type=StabilityStudyType.LONG_TERM,
            condition="30C/65%RH",
            duration_months=24,
            batch_analysis=batch,
            packaging=pack,
            protocol=(
                "ICH Q1A(R2) long-term condition for Zone IVb. Tested at 0, 6, 12, 18 "
                "and 24 months against the finished-product specification (3.2.P.5.1)."
            ),
        )
        study.results = results_at(
            product.specification, LONG_TERM_TIMEPOINTS, values
        )
        product.stability.append(study)

    # ---- 3.2.P.8: accelerated, on the first batch only -------------------
    # One batch, because accelerated data answers a different question --
    # "does anything change fast?" -- and three copies of that answer add
    # nothing to the fixture.
    if product.batch_analyses:
        accelerated = StabilityStudy(
            study_type=StabilityStudyType.ACCELERATED,
            condition="40C/75%RH",
            duration_months=6,
            batch_analysis=product.batch_analyses[0],
            packaging=pack,
            protocol="ICH Q1A(R2) accelerated condition. Tested at 0, 3 and 6 months.",
        )
        accelerated.results = results_at(
            product.specification, ACCELERATED_TIMEPOINTS, DRUG_PRODUCT_ACCELERATED
        )
        product.stability.append(accelerated)

    # ---- 3.2.S.7: the drug substance's own studies -----------------------
    for api in product.apis:
        if api.stability or not api.batch_analyses:
            continue
        # The retest period is the substance's analogue of a shelf life,
        # and R05 checks it against exactly this data. Set only when the
        # seed has not already declared one -- the data supports the claim,
        # not the other way round.
        if api.retest_period_months is None:
            api.retest_period_months = 24
        study = StabilityStudy(
            study_type=StabilityStudyType.LONG_TERM,
            condition="30C/65%RH",
            duration_months=24,
            batch_analysis=api.batch_analyses[0],
            packaging=_substance_pack(product, api),
            protocol=(
                "ICH Q1A(R2) long-term condition. Supports the retest period declared "
                "in 3.2.S.7.1; tested against the drug substance specification "
                "(3.2.S.4.1)."
            ),
        )
        study.results = results_at(
            api.specification, LONG_TERM_TIMEPOINTS, DRUG_SUBSTANCE_LONG_TERM
        )
        api.stability.append(study)
