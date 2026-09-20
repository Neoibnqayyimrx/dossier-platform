"""Context builders for the stability sections (P21): 3.2.S.7.1-.3 and
3.2.P.8.1-.3.

Three sections, twice -- once for the drug substance, once for the
finished product -- built from three shapes:

    .1  the SUMMARY: what the data supports, and the conclusion drawn.
    .2  the post-approval PROTOCOL and COMMITMENT.
    .3  the DATA: timepoint x test, per study.

WHY they share builders across the two owners, exactly as
quality_control.py's do: 3.2.S.7 and 3.2.P.8 are the same section asked of
two different materials. Written as six builders they would be six places
for the same table to be laid out differently, and the drift between
near-duplicate sections of one dossier is what this platform exists to
catch.

## The one thing that matters most in this file

**3.2.x.7/8.1 does not print a claimed shelf life. It prints what the
timepoint data supports.**

The old 3.2.P.8.1 rendered `product.shelf_life_months` beside a free-text
`result_summary`, so the section could state 24 months over a table
showing dissolution failing at 12 -- and the platform would render it
without complaint. Now the supported figure is computed by
`app.models.stability.supported_months`, the same function rule R05
checks against, and where the claim exceeds it the section says so in the
document rather than repeating the claim. A summary that can contradict
the table beneath it is the defect class this whole project exists to
eliminate; it must not be reachable through a template.

Everything here is synchronous, DB-free and Word-library-free, like
context.py and quality_control.py -- these take already-loaded ORM objects
and return a plain dict.
"""

from __future__ import annotations

from app.models.enums import SpecificationOwnerKind, StabilityStudyType
from app.models.stability import supported_months
from app.templating.quality_control import (
    MISSING,
    OWNER_LABEL,
    _owner_kind_of,
    owner_name,
    specification_rows,
)

# What each owner's claim is CALLED. A finished product has a shelf life;
# a drug substance has a retest period, which is not an expiry but the
# interval after which the material must be re-tested before use. Printing
# "shelf life" on 3.2.S.7.1 would be a regulatory error on the page, not a
# wording preference.
CLAIM_LABEL: dict[SpecificationOwnerKind, str] = {
    SpecificationOwnerKind.DRUG_SUBSTANCE: "Retest period",
    SpecificationOwnerKind.DRUG_PRODUCT: "Shelf life",
}


def claimed_months(owner) -> int | None:
    """The claim this owner makes, however its own model spells the field."""
    for attribute in ("shelf_life_months", "retest_period_months"):
        value = getattr(owner, attribute, None)
        if value is not None:
            return int(value)
    return None


def _study_rows(studies) -> list[dict]:
    """One row per study for the summary's study table: what was run, on
    which batch, in which pack, and how far it holds.

    The batch and the pack are columns rather than a footnote because they
    are what an assessor cross-references -- the batch number against
    3.2.P.5.4, the pack against 3.2.P.7. A study table without them names
    conditions and hides the material.
    """
    rows = []
    for study in sorted(studies, key=lambda s: (s.study_type.value, s.condition, _batch_number(s))):
        supported = study.longest_passing_timepoint
        rows.append(
            {
                "study_type": study.study_type.value,
                "condition": study.condition,
                "batch_number": _batch_number(study) or MISSING,
                "pack": study.packaging.description if study.packaging else MISSING,
                "duration_months": study.duration_months,
                "timepoints": ", ".join(str(t) for t in study.timepoints) or "none recorded",
                # "not yet entered" and "0" are different answers, and the
                # column has to keep them apart: one is a study whose data
                # has not been typed, the other is a study that failed at
                # its first timepoint.
                "supported_months": (
                    "no timepoint data" if supported is None else f"{supported} months"
                ),
            }
        )
    return rows


def _batch_number(study) -> str | None:
    return study.batch_analysis.batch_number if study.batch_analysis else None


def stability_summary_context(section, owner, narrative) -> dict:
    """3.2.S.7.1 / 3.2.P.8.1 -- the summary and conclusion.

    HYBRID, and the split is precise: every number is computed, and the
    narrative slot carries the CONCLUSION only -- the applicant's reading
    of the data, which is a judgement and genuinely theirs to write. What
    the slot cannot do is state a period, because the period is printed
    above it from the data.
    """
    studies = list(owner.stability)
    long_term = [s for s in studies if s.study_type is StabilityStudyType.LONG_TERM]
    supported, basis = supported_months(long_term)
    claimed = claimed_months(owner)
    label = CLAIM_LABEL[_owner_kind_of(owner)]

    return {
        "section_number": section.number,
        "section_title": section.title,
        "owner_label": OWNER_LABEL[_owner_kind_of(owner)],
        "owner_name": owner_name(owner),
        "claim_label": label,
        "claim_statement": _claim_statement(label, claimed, supported, basis, studies),
        "storage_statement": _storage_statement(owner, studies),
        "studies": _study_rows(studies),
        # The tests the studies actually report on, so the summary says
        # WHAT was monitored without repeating the data table under it.
        # ICH Q1A(R2) 2.2.6: stability testing covers the attributes
        # susceptible to change, not the whole release specification.
        "tests_monitored": _tests_monitored(studies),
        "narrative": narrative,
    }


def _claim_statement(label, claimed, supported, basis, studies) -> str:
    """The load-bearing sentence of the section, and the reason this
    builder exists rather than a template placeholder.

    Four cases, and the third is the one that matters:

    1. No studies at all -- say so; there is no period to state.
    2. Nothing claimed yet -- print what the data supports and leave the
       claim to be made.
    3. **The claim exceeds the data.** The section does NOT print the
       claim. It prints a marker naming both figures, which renders into
       the document an assessor reads and which rule R05 has already
       blocked the export over. Printing the claim here would produce a
       page asserting a shelf life the next section disproves.
    4. The claim is supported -- state it, with the evidence behind it.
    """
    if not studies:
        return (
            f"[[NO STABILITY DATA ON FILE -- no {label.lower()} can be stated from this "
            f"dossier's own data]]"
        )
    if claimed is None:
        return (
            f"The long-term data support {supported} months, based on {basis}. "
            f"No {label.lower()} has been declared yet."
        )
    if claimed > supported:
        return (
            f"[[{label.upper()} NOT SUPPORTED: {claimed} months is claimed, but the "
            f"long-term data support {supported} months ({basis}). This section cannot "
            f"state the claimed period -- see the data in the corresponding stability "
            f"data section, and rule R05.]]"
        )
    return (
        f"{label}: {claimed} months. The long-term data support {supported} months, "
        f"based on {basis}, at every test in the specification."
    )


def _storage_statement(owner, studies) -> str:
    """The storage condition, taken from the product where it is declared
    and cross-checked against the conditions actually studied.

    An assessor reads the label's storage statement and the study
    conditions together: a product labelled "store below 25 C" whose only
    long-term study ran at 30 C is a mismatch that gets queried.
    """
    declared = getattr(owner, "storage_condition", None)
    conditions = sorted(
        {s.condition for s in studies if s.study_type is StabilityStudyType.LONG_TERM}
    )
    if not conditions:
        studied = "no long-term condition is on file"
    else:
        studied = f"long-term data were generated at {', '.join(conditions)}"
    if declared:
        # The declared condition is a sentence the filer typed and usually
        # ends in a full stop of its own; adding another produces
        # "...light.." on the page. Trimmed rather than left, because a
        # rendered document is the artefact an assessor reads.
        return f"Recommended storage: {declared.rstrip('. ')}. The {studied}."
    return f"[[NO STORAGE CONDITION DECLARED]] The {studied}."


def _tests_monitored(studies) -> list[str]:
    """Which specification tests the studies report on, in specification
    order. Names only -- the values are the data section's job, and
    repeating them here is how the two come to disagree."""
    ordered: dict[int, str] = {}
    for study in studies:
        for result in study.results:
            test = result.specification_test
            if test is not None:
                ordered[test.sort_order] = test.test_name
    return [name for _, name in sorted(ordered.items())]


def stability_data_context(section, owner) -> dict:
    """3.2.S.7.3 / 3.2.P.8.3 -- the data itself.

    One block per study, because a study IS the unit an assessor reads:
    this batch, this condition, this pack. Merging three batches into one
    table would lose the axis that makes the numbers mean anything.

    Inside each block, ONE ROW PER TEST PER TIMEPOINT, with the acceptance
    criterion on the same line as the value. WHY not the matrix a stability
    report uses (tests down, timepoints across): docxtpl's column loop
    (`{%tc %}`) has the same "the tag needs a cell of its own" constraint
    `{%tr %}` has, and nesting one inside the other is what P20's build log
    records dying with "Encountered unknown tag 'endfor'". The flat form is
    also the better document, which is the honest reason to prefer it -- a
    limit printed in one table and the numbers judged against it in another
    is the layout that lets an out-of-specification result pass unnoticed.

    Each row carries its own verdict, derived through the result's
    specification test. The document therefore SHOWS which cells are out of
    specification, rather than leaving an assessor to compare eight columns
    by eye -- which is exactly the comparison they would otherwise be doing
    by hand, and the one rule R23 blocks the export over.
    """
    blocks = []
    for study in sorted(
        owner.stability, key=lambda s: (s.study_type.value, s.condition, _batch_number(s) or "")
    ):
        by_test = {}
        for result in study.results:
            by_test.setdefault(result.specification_test_id, []).append(result)

        rows = []
        for test in specification_rows(owner):
            for result in sorted(by_test.get(test.id, []), key=lambda r: r.timepoint_months):
                rows.append(
                    {
                        "test_name": test.test_name,
                        "acceptance_criterion": test.acceptance_criterion,
                        "timepoint_months": result.timepoint_months,
                        "result": result.result,
                        "verdict": _verdict_word(result.meets_criterion),
                    }
                )
        blocks.append(
            {
                "study_type": study.study_type.value,
                "condition": study.condition,
                "batch_number": _batch_number(study) or MISSING,
                "pack": study.packaging.description if study.packaging else MISSING,
                "duration_months": study.duration_months,
                "protocol": study.protocol or MISSING,
                "rows": rows,
                "no_results_statement": (
                    ""
                    if rows
                    else (
                        f"[[NO TIMEPOINT RESULTS ON FILE for this study -- "
                        f"{section.number} cannot be completed]]"
                    )
                ),
            }
        )

    return {
        "section_number": section.number,
        "section_title": section.title,
        "owner_label": OWNER_LABEL[_owner_kind_of(owner)],
        "owner_name": owner_name(owner),
        "studies": blocks,
        "no_studies_statement": (
            ""
            if blocks
            else (
                f"[[NO STABILITY STUDIES ON FILE for {owner_name(owner)} -- "
                f"{section.number} cannot be completed]]"
            )
        ),
    }


def _verdict_word(verdict: bool | None) -> str:
    """Three outcomes, three words. "Not checked" is NOT "Meets" -- the
    distinction app/validation/acceptance.py is built to preserve has to
    survive into the rendered page, or the document quietly credits every
    result nothing could parse."""
    if verdict is True:
        return "Meets"
    if verdict is False:
        return "OUT OF SPECIFICATION"
    return "Not checked mechanically"


def stability_commitment_context(section, owner, narrative) -> dict:
    """3.2.S.7.2 / 3.2.P.8.2 -- the post-approval protocol and commitment.

    What the section is for: the studies filed with the application are
    usually incomplete -- twelve months of data supporting a twenty-four
    month claim is the ordinary case -- and the applicant undertakes to
    continue them, to put the first production batches on stability, and to
    report any out-of-specification result to the agency. That undertaking
    is the commitment; the schedule it will follow is the protocol.

    HYBRID, and the split is the same as .1's: the protocol table is
    generated (which batches are still running, to what duration, at which
    condition, tested for what), and the narrative slot carries the
    commitment's own wording, which is a legal undertaking the applicant
    makes and not a number the platform can derive.

    The generated half is what stops the commonest failure here: a
    commitment that names batches or timepoints the stability section does
    not contain. Every row below is read from the studies themselves.
    """
    claimed = claimed_months(owner)
    rows = []
    for study in sorted(
        owner.stability, key=lambda s: (s.study_type.value, s.condition, _batch_number(s) or "")
    ):
        if study.study_type is StabilityStudyType.ACCELERATED:
            # An accelerated study runs six months and is finished. There
            # is nothing to commit to continuing, and listing it in a
            # continuation protocol would promise work nobody will do.
            continue
        tested_to = max(study.timepoints, default=0)
        target = max(study.duration_months, claimed or 0)
        rows.append(
            {
                "batch_number": _batch_number(study) or MISSING,
                "condition": study.condition,
                "pack": study.packaging.description if study.packaging else MISSING,
                "tested_to_months": tested_to,
                "target_months": target,
                "remaining": ("Complete" if tested_to >= target else f"To {target} months"),
            }
        )

    return {
        "section_number": section.number,
        "section_title": section.title,
        "owner_label": OWNER_LABEL[_owner_kind_of(owner)],
        "owner_name": owner_name(owner),
        "claim_label": CLAIM_LABEL[_owner_kind_of(owner)],
        "claim_months": claimed if claimed is not None else MISSING,
        "protocol": rows,
        "no_studies_statement": (
            ""
            if rows
            else (
                f"[[NO ONGOING LONG-TERM STUDY ON FILE for {owner_name(owner)} -- "
                f"{section.number} has no protocol to describe]]"
            )
        ),
        "narrative": narrative,
    }
