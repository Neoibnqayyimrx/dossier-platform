"""Context builders for the bioequivalence documents (P22).

Four leaves, one set of study data, spread across three modules:

    1.4.1    the Bioequivalence Trial Information form   (Module 1)
    5.2      the tabular listing of all clinical studies  (Module 5)
    5.3.1.2  a structured summary of the study            (Module 5)
    1.2.17 / 1.2.18   the two biowaiver requests          (Module 1)

## Why that spread is the point of the phase

A regulatory affairs officer assembling this by hand types the same
confidence intervals onto an agency form in Module 1, into a summary table
in Module 5, and into the covering summary that sits with the CRO's report
-- three times, from a PDF, under deadline. The three then have to agree,
and an assessor cross-reads exactly those three. This module is the reason
they cannot disagree: every number below is read from
`BioequivalenceResult`, and none of them is typed anywhere.

1.4.1 is the sharpest case. It is a **Module 1** document produced with no
prose at all out of **Module 5** numbers -- the clearest demonstration in
the platform of why the single-source-of-truth premise matters, and the
leaf that could not exist while a bioequivalence study was a paragraph.

## Where the acceptance window comes from

Never from this module, and never from the rule that checks it. Both ask
`RegionProfile.window_for(product)` (app/ctd/region_profiles.py), so the
window a document PRINTS and the window rule R25 CHECKS are one value --
the same discipline `supported_months` enforces between 3.2.P.8.1 and R05.

Everything here is synchronous, DB-free and Word-library-free, like
context.py: it takes already-loaded ORM objects and returns a plain dict.
"""

from __future__ import annotations

from decimal import Decimal

from app.ctd.region_profiles import BioequivalenceWindow, get_region_profile
from app.models.enums import BiowaiverKind
from app.templating.quality_control import MISSING

# What a rendered document says where a study has no interval on file for a
# parameter. Distinct from MISSING because the two are different failures:
# MISSING is a field nobody filled in, this is a parameter the study did
# not report at all, which is a question for the CRO.
NOT_REPORTED = "[[NOT REPORTED]]"


# The order the parameters are printed in, everywhere. Cmax first because
# that is the order every bioequivalence report and every agency form uses
# -- rate of absorption, then extent.
#
# WHY the order lives here and not in a `sorted()` at each call site: the
# BTI form, the tabular listing and the study summary all print the same
# three rows, and three independent sort keys is three chances for one
# document to disagree with another about which parameter failed.
def _sorted_results(study) -> list:
    return sorted(study.results, key=lambda r: (r.sort_order, r.parameter.value))


def window_for(project) -> BioequivalenceWindow:
    """The acceptance window this project's studies are judged against.

    Falls back to the ICH/WHO window for a region with no profile at all
    (FDA today), rather than raising: a rendered document with no window
    on it would be a form with an empty box where the criterion belongs,
    and every agency in the world starts from 80.00-125.00 %.
    """
    try:
        profile = get_region_profile(project.region)
    except KeyError:
        from app.ctd.region_profiles import DEFAULT_BE_WINDOW

        return DEFAULT_BE_WINDOW
    return profile.window_for(project.product)


def _percent(value) -> str:
    """A percentage as the two-decimal figure a study report states.

    Two decimals is not cosmetic: the window itself is written to two
    ("80.00 - 125.00 %"), and a lower bound of 80.0 printed against a limit
    of 80.00 invites the reader to wonder which way 79.996 was rounded.
    """
    if value is None:
        return NOT_REPORTED
    return f"{Decimal(value):.2f}"


def result_rows(study, window: BioequivalenceWindow) -> list[dict]:
    """One row per pharmacokinetic parameter: the ratio, the interval, and
    the verdict against `window`.

    The verdict is computed here and stored nowhere -- see
    `BioequivalenceResult`'s docstring on why a stored pass/fail would
    freeze one region's window into the data.
    """
    rows = []
    for result in _sorted_results(study):
        breached = result.outside(window.lower, window.upper)
        rows.append(
            {
                "parameter": result.parameter.value,
                "geometric_mean_ratio": _percent(result.geometric_mean_ratio),
                "ci_lower": _percent(result.ci_lower),
                "ci_upper": _percent(result.ci_upper),
                "intra_subject_cv": _percent(result.intra_subject_cv),
                "window": window.label,
                # Names the BOUND, not just "fail". A filer reading "the
                # lower bound is outside" learns their product
                # under-performed; "the upper bound is outside" is a
                # different problem with the same product.
                "verdict": (
                    "within the acceptance window"
                    if not breached
                    else "OUTSIDE the acceptance window (" + " and ".join(breached) + " bound)"
                ),
            }
        )
    return rows


def study_fails(study, window: BioequivalenceWindow) -> bool:
    """Whether any parameter of `study` falls outside `window`.

    One function, used by the renderers and by rule R25, so a document
    cannot call a study bioequivalent while the rule blocks the export
    over it.
    """
    return any(result.outside(window.lower, window.upper) for result in study.results)


def _subject_summary(study) -> str:
    """ "24 enrolled, 22 completed (2 withdrew)" -- assembled once.

    Dropouts are stated rather than left to be subtracted by the reader:
    they are what an assessor checks the study's power against, and a form
    that prints only the enrolled figure overstates the study.
    """
    if study.subjects_enrolled is None and study.subjects_completed is None:
        return MISSING
    if study.subjects_enrolled is None:
        return f"{study.subjects_completed} completed"
    if study.subjects_completed is None:
        return f"{study.subjects_enrolled} enrolled"
    dropouts = study.dropouts
    tail = f" ({dropouts} withdrew)" if dropouts else ""
    return f"{study.subjects_enrolled} enrolled, {study.subjects_completed} completed{tail}"


def _comparator(study) -> str:
    reference = study.reference_product
    return reference.identity if reference is not None else MISSING


def _test_batch(study) -> str:
    if study.test_batch is not None:
        return study.test_batch.batch_number
    return MISSING


# ---------------------------------------------------------------------------
# 1.4.1 -- Bioequivalence Trial Information form
# ---------------------------------------------------------------------------


def bti_context(section, project) -> dict:
    """The BTI form: label/value rows plus the results table.

    ## Why rows rather than fixed template placeholders

    Same call 3.2.S.1's nomenclature table makes: which facts a study
    actually has on file varies (not every study records a CRO, not every
    comparator has a purchase country), and a form of blank boxes reads as
    missing data rather than as "not applicable". The rows that exist are
    printed; the ones that do not, are not.

    ## Why there is no narrative slot anywhere in this document

    The target TOC's own note on this leaf reads: "Derived entirely from
    the BE study data. No prose." An agency reads a form field by field
    against the study report. A drafted paragraph on it could state a
    confidence interval the table below disproves -- which is the exact
    defect the whole platform exists to make unreachable.
    """
    product = project.product
    window = window_for(project)
    studies = list(product.bioequivalence_studies)

    blocks = []
    for study in studies:
        reference = study.reference_product
        rows = [
            ("Study number", study.study_identifier),
            ("Study title", study.title or MISSING),
            ("Design", study.design_summary),
            ("Subjects", _subject_summary(study)),
            ("Analyte measured", study.analyte or MISSING),
            ("Bioanalytical method", study.bioanalytical_method or MISSING),
            ("Contract research organisation", study.cro_name or MISSING),
            ("Study site", study.study_site or MISSING),
            (
                "Study period",
                (
                    f"{study.start_date} to {study.completion_date}"
                    if study.start_date and study.completion_date
                    else MISSING
                ),
            ),
            ("Test product batch", _test_batch(study)),
            (
                "Test product batch size",
                (
                    f"{study.test_batch_size_units:,} units"
                    if study.test_batch_size_units is not None
                    else MISSING
                ),
            ),
            (
                "Test product manufacture date",
                (
                    str(study.test_batch_manufacture_date)
                    if study.test_batch_manufacture_date
                    else MISSING
                ),
            ),
            ("Reference product", reference.name if reference else MISSING),
            ("Reference product strength", (reference.strength if reference else None) or MISSING),
            (
                "Reference product manufacturer",
                (reference.manufacturer if reference else None) or MISSING,
            ),
            (
                "Reference product country of origin",
                (reference.country_of_origin if reference else None) or MISSING,
            ),
            ("Reference product batch", (reference.batch_number if reference else None) or MISSING),
            (
                "Reference product expiry",
                str(reference.expiry_date) if reference and reference.expiry_date else MISSING,
            ),
        ]
        blocks.append(
            {
                "study_identifier": study.study_identifier,
                "details": [{"label": label, "value": value} for label, value in rows],
                "results": result_rows(study, window),
                # Stated in the document, not only in a validation report:
                # a form that prints a failing interval without saying it
                # fails is a form that has to be re-checked by hand.
                "conclusion": (
                    "One or more confidence intervals fall outside the acceptance window; "
                    "bioequivalence is NOT demonstrated on this data."
                    if study_fails(study, window)
                    else "All confidence intervals fall within the acceptance window; "
                    "bioequivalence is demonstrated."
                ),
            }
        )

    return {
        "section_number": section.number,
        "section_title": section.title,
        "product": product,
        "product_name": product.brand_name,
        "generic_name": product.generic_name,
        "strength": product.strength_display or MISSING,
        "dosage_form": product.dosage_form.value if product.dosage_form else MISSING,
        "applicant_name": (project.applicant.company_name if project.applicant else MISSING),
        "acceptance_window": window.label,
        "narrow_therapeutic_index": bool(product.narrow_therapeutic_index),
        "studies": blocks,
        # WHY the form still renders with no study on file, rather than
        # being skipped: an applicable leaf that quietly disappears is the
        # gap nobody sees. R06 blocks the export; this page says why.
        "no_studies_statement": (
            ""
            if blocks
            else "No bioequivalence study is on file for this product. This form cannot be "
            "completed until the study data is entered (rule R06)."
        ),
    }


# ---------------------------------------------------------------------------
# 5.2 -- Tabular listing of all clinical studies
# ---------------------------------------------------------------------------


def clinical_listing_context(section, project) -> dict:
    """5.2, generated by WALKING the studies present.

    The target TOC's note on this leaf is the whole specification: "Must
    not be able to disagree with what is actually filed under 5.3.1." A
    hand-typed listing is the single most common Module 5 defect there is
    -- a study is dropped from the dossier late and the listing still
    names it, or a study is added and the listing is not updated. Here the
    listing has no independent existence: it is `bioequivalence_studies`
    and `clinical` rendered as a table, so a study cannot be in one and
    not the other.
    """
    product = project.product
    window = window_for(project)

    rows = []
    for study in product.bioequivalence_studies:
        rows.append(
            {
                "study_identifier": study.study_identifier,
                "kind": "Comparative BA / bioequivalence",
                "design": study.design_summary,
                "subjects": _subject_summary(study),
                "comparator": _comparator(study),
                "analyte": study.analyte or MISSING,
                # The LEAF the full report is filed at, printed in the
                # table. This is what makes the listing navigable rather
                # than decorative -- an assessor reads it to find the
                # report, not to learn that a study exists.
                "location": "5.3.1.2",
                "outcome": (
                    "Bioequivalence NOT demonstrated on this data"
                    if study_fails(study, window)
                    else "Bioequivalent within " + window.label
                ),
            }
        )

    # The other clinical entries -- literature and any other clinical study
    # -- belong in this listing too. The section is "all clinical studies",
    # and a listing that covered only the bioequivalence study would be a
    # listing that disagrees with 5.4.
    for entry in product.clinical:
        rows.append(
            {
                "study_identifier": MISSING,
                "kind": entry.kind.value,
                "design": MISSING,
                "subjects": MISSING,
                "comparator": MISSING,
                "analyte": MISSING,
                "location": "5.4" if entry.kind.value == "literature" else "5.3.1",
                "outcome": entry.summary,
            }
        )

    return {
        "section_number": section.number,
        "section_title": section.title,
        "product_name": product.brand_name,
        "generic_name": product.generic_name,
        "rows": rows,
        "no_studies_statement": (
            "" if rows else "No clinical study or literature reference is on file for this product."
        ),
    }


# ---------------------------------------------------------------------------
# 5.3.1.2 -- the structured summary that ships beside the CRO's report
# ---------------------------------------------------------------------------


def be_study_summary_context(section, project) -> dict:
    """A structured summary of every bioequivalence study on file.

    ## What this document is, and what it is NOT

    It is NOT the study report. The report is the CRO's, it runs to
    hundreds of pages, nobody here can author it, and it is UPLOADED at
    this same leaf (P18). This is the summary that sits beside it: the
    design, the comparator, the batches, and the confidence intervals, in
    the platform's own layout, generated from the data the rules check.

    ## Why it is a separate leaf rather than replacing the upload

    Assembly lets an uploaded file win over a rendered one at the same key
    -- correctly, because a generated stand-in for a signed document is
    not an improvement on it. So this spec carries `leaf_suffix="summary"`
    and the two ship as two files under one heading, which is what the
    eCTD DTD's `leaf*` content model for this element permits anyway.
    Without that, attaching the report would silently delete this summary.
    """
    product = project.product
    window = window_for(project)

    blocks = []
    for study in product.bioequivalence_studies:
        reference = study.reference_product
        blocks.append(
            {
                "study_identifier": study.study_identifier,
                "title": study.title or MISSING,
                "design": study.design_summary,
                "subjects": _subject_summary(study),
                "analyte": study.analyte or MISSING,
                "bioanalytical_method": study.bioanalytical_method or MISSING,
                "cro_name": study.cro_name or MISSING,
                "study_site": study.study_site or MISSING,
                "comparator": _comparator(study),
                "comparator_batch": (reference.batch_number if reference else None) or MISSING,
                "comparator_expiry": (
                    str(reference.expiry_date) if reference and reference.expiry_date else MISSING
                ),
                "test_batch": _test_batch(study),
                "test_batch_size": (
                    f"{study.test_batch_size_units:,} units"
                    if study.test_batch_size_units is not None
                    else MISSING
                ),
                "results": result_rows(study, window),
                "conclusion": (
                    "Bioequivalence is NOT demonstrated: one or more 90 % confidence "
                    f"intervals fall outside {window.label}."
                    if study_fails(study, window)
                    else f"All 90 % confidence intervals fall within {window.label}. "
                    "Bioequivalence is demonstrated."
                ),
            }
        )

    return {
        "section_number": section.number,
        "section_title": section.title,
        "product_name": product.brand_name,
        "strength": product.strength_display or MISSING,
        "acceptance_window": window.label,
        "studies": blocks,
        "no_studies_statement": (
            ""
            if blocks
            else "No bioequivalence study data is on file. The study report filed at this "
            "leaf has no structured summary to accompany it."
        ),
    }


# ---------------------------------------------------------------------------
# 1.2.17 / 1.2.18 -- the biowaiver requests
# ---------------------------------------------------------------------------

_BIOWAIVER_BASIS = {
    BiowaiverKind.BCS_BASED: (
        "Biopharmaceutics Classification System: the drug substance is highly soluble "
        "and the drug product rapidly dissolving, so in vivo bioequivalence may be "
        "demonstrated in vitro."
    ),
    BiowaiverKind.ADDITIONAL_STRENGTH: (
        "Proportional composition and comparable in vitro dissolution against the "
        "strength on which the in vivo study was conducted."
    ),
}


def biowaiver_context(section, project, narrative) -> dict:
    """1.2.17 (BCS-based) or 1.2.18 (additional strength).

    HYBRID, and the split is precise. The BCS class, the f2 similarity
    factor and the study being leaned on are data and are printed from it.
    The argument that ties them together -- why THIS product, on THIS
    evidence, does not need a human study -- is a regulatory judgement the
    applicant makes and signs, so it is the narrative slot.

    Which requests appear on the page is filtered by `kind`, not by which
    rows happen to exist: a BCS request rendered onto the additional-
    strength leaf would put the wrong claim at the wrong number, and an
    assessor reads Module 1 by number.
    """
    product = project.product
    kind = (
        BiowaiverKind.BCS_BASED if section.number == "1.2.17" else BiowaiverKind.ADDITIONAL_STRENGTH
    )
    requests = [w for w in product.biowaivers if w.kind is kind]

    blocks = []
    for waiver in requests:
        rows = [("Strength covered by this request", waiver.strength)]
        if kind is BiowaiverKind.BCS_BASED:
            rows.append(
                (
                    "BCS class",
                    f"Class {waiver.bcs_class}" if waiver.bcs_class is not None else MISSING,
                )
            )
        if waiver.dissolution_similarity_f2 is not None:
            # f2 >= 50 is the accepted threshold for similar dissolution
            # profiles. Printing the verdict beside the number, not just
            # the number, for the same reason every other table here does.
            f2 = Decimal(waiver.dissolution_similarity_f2)
            rows.append(
                (
                    "Dissolution similarity factor (f2)",
                    f"{f2:.2f} ({'similar' if f2 >= 50 else 'NOT similar'}; the accepted "
                    f"threshold is f2 ≥ 50)",
                )
            )
        if waiver.supporting_study is not None:
            rows.append(
                (
                    "Supported by in vivo study",
                    f"{waiver.supporting_study.study_identifier} (filed at 5.3.1.2)",
                )
            )
        blocks.append(
            {
                "strength": waiver.strength,
                "basis": _BIOWAIVER_BASIS[kind],
                "details": [{"label": label, "value": value} for label, value in rows],
            }
        )

    return {
        "section_number": section.number,
        "section_title": section.title,
        "product_name": product.brand_name,
        "generic_name": product.generic_name,
        "dosage_form": product.dosage_form.value if product.dosage_form else MISSING,
        "requests": blocks,
        # The leaf only renders at all when the filer has answered "yes" to
        # its conditional question (SectionSpec.only_when_applicable), so an
        # empty page here means the claim was made and its evidence never
        # entered -- which is worth saying on the page rather than shipping
        # a request with nothing in it.
        "no_requests_statement": (
            ""
            if blocks
            else "This biowaiver has been claimed for this filing, but no supporting data "
            "has been entered. The request cannot be assessed as it stands."
        ),
        "narrative": narrative,
    }
