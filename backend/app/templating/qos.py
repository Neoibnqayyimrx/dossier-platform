"""The Quality Overall Summary in full, leaf 2.3 (P24c).

## What changed, and why "registered" was not "done"

2.3 has been registered since P04 and rendering since P07 -- as a page with
one narrative slot and a structural formula. The target TOC lists fourteen
subsections under it (2.3.S.1 to 2.3.S.7 and 2.3.P.1 to 2.3.P.7), and its
note on this leaf is blunt about the difference: "Treat 'registered' and
'complete' as different statuses here."

They are different because the thin version was not the QOS an assessor
reads. A QOS is the document a reviewer opens FIRST and navigates the whole
of Module 3 from; ICH M4Q gives it a section-by-section structure that
mirrors the body of data exactly, so that a reviewer reading 2.3.S.4 knows
where 3.2.S.4 is and what it should say.

## The defect this exists to eliminate

A QOS that can drift from Module 3. It is the most commonly raised quality
deficiency there is, and the mechanism is always the same: the QOS is
written near the end of a project from a previous product's QOS, then
Module 3 changes during review and the summary does not. An assessor
cross-reads 2.3.P.8 against 3.2.P.8.1, finds two shelf lives, and now
distrusts the whole submission -- reasonably, because they cannot tell
which document the applicant believes.

So every value here is pulled through `app.templating.derived` out of the
context dict the corresponding Module 3 section renders from, exactly as
the QIS is (P24b). The QOS is never handed a model.

## Where the narrative slots are, and why only there

A QOS is not only a re-presentation -- it is a SUMMARY, and summarising
involves judgement. "The process is a conventional wet granulation whose
critical steps are controlled by the in-process limits in 3.2.P.3.4" is an
argument, and it is the applicant's to make.

Three slots, one per place where genuine summary judgement is owed:

  * `drug_substance_summary`  -- the case for the substance's control
  * `drug_product_summary`    -- the case for the product's control
  * `overview`                -- the one-paragraph orientation, kept from
                                 the thin version so nothing regressed

**No slot can carry a number**, because every number is printed from the
derived blocks above it. That is the line: the data is derived, the
argument is written, and an argument that contradicts the data beside it is
visible on the same page rather than three hundred pages away.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field

from app.templating.derived import (
    SourcedValue,
    context_for,
    field,
    rows,
    section_contexts,
)
from app.templating.instances import expand_sections


@dataclass(frozen=True)
class QosSubsection:
    """One numbered subsection of the QOS.

    `number` is the QOS's own numbering (2.3.S.4), and `mirrors` is the
    Module 3 section it summarises (3.2.S.4). Both are printed: the first
    is where the assessor is, the second is where they go next. A QOS
    subsection that does not name what it mirrors makes the reviewer do the
    mapping in their head, which is the one thing the structure exists to
    spare them.
    """

    number: str
    title: str
    mirrors: str
    values: list[SourcedValue] = dataclass_field(default_factory=list)
    table_caption: str = ""
    table_columns: list[str] = dataclass_field(default_factory=list)
    table_rows: list[dict] = dataclass_field(default_factory=list)


def qos_context(section, project, narrative) -> dict:
    """2.3, assembled from Module 3's own rendered contexts."""
    contexts = section_contexts(project)
    substances = [instance for instance in expand_sections(project) if instance.number == "3.2.S.1"]

    return {
        "product": project.product,
        "section_number": section.number,
        "section_title": section.title,
        # Kept from the pre-P24 version. Removing it would have been a
        # regression in the one thing the thin QOS did well: a paragraph
        # that says what the product is before the structure begins.
        "narrative": narrative,
        "drug_substances": [
            {
                "name": instance.subject.inn_name,
                "subsections": _drug_substance_subsections(contexts, instance.subject_slug),
            }
            for instance in substances
        ],
        "drug_product_subsections": _drug_product_subsections(contexts),
        "derivation_note": (
            "Every value in this summary is rendered from the same data as the Module 3 "
            "section named beside it, so this summary cannot state a value that Module 3 "
            "does not. The drafted paragraphs summarise; they carry no figures."
        ),
    }


def _batches_value(contexts, key: str) -> SourcedValue:
    """The batches a control section files, as one summary line.

    WHY this is not just `field(contexts, key, "no_batches_statement", ...)`:
    that field is EMPTY when batches exist -- it is the marker 3.2.S.4.4
    prints only in their absence -- so the QOS rendered a line reading
    "Batches:" with nothing after it, on every dossier that had batches.
    A summary line that goes blank precisely when the news is good is
    worse than no line.

    So the numbers themselves are summarised, from the same rows the batch
    analysis section tabulates, and the marker is used only when there are
    none.
    """
    batches = rows(contexts, key, "batches")
    if not batches:
        return field(contexts, key, "no_batches_statement", "Batches")
    numbers = ", ".join(batch["batch_number"] for batch in batches)
    return SourcedValue(label="Batches filed", value=numbers, source=key)


def _drug_substance_subsections(contexts, slug: str) -> list[QosSubsection]:
    """2.3.S.1 to 2.3.S.7, for ONE active ingredient.

    Repeated per substance, exactly as 3.2.S is, and for the same reason:
    a combination product's QOS that summarised "the drug substance" would
    summarise one of two materials and say nothing about which.
    """
    general = f"3.2.S.1-{slug}"
    manufacturer = f"3.2.S.2.1-{slug}"
    impurities = f"3.2.S.3.2-{slug}"
    specification = f"3.2.S.4.1-{slug}"
    batches = f"3.2.S.4.4-{slug}"
    standards = f"3.2.S.5-{slug}"
    container = f"3.2.S.6-{slug}"
    stability = f"3.2.S.7.1-{slug}"

    return [
        QosSubsection(
            number="2.3.S.1",
            title="General Information",
            mirrors="3.2.S.1",
            table_caption="Nomenclature and identity",
            table_columns=["Item", "Value"],
            table_rows=[
                {"cells": [row["label"], str(row["value"])]}
                for row in rows(contexts, general, "nomenclature")
            ],
        ),
        QosSubsection(
            number="2.3.S.2",
            title="Manufacture",
            mirrors="3.2.S.2",
            table_caption="Manufacturer and coverage",
            table_columns=["Item", "Value"],
            table_rows=[
                {"cells": [row["label"], str(row["value"])]}
                for row in rows(contexts, manufacturer, "manufacturer_details")
            ],
        ),
        QosSubsection(
            number="2.3.S.3",
            title="Characterisation",
            mirrors="3.2.S.3",
            table_caption="Impurity profile",
            table_columns=["Impurity", "Type", "Limit", "Basis"],
            table_rows=[
                {
                    "cells": [
                        row["name"],
                        row["impurity_type"],
                        row["limit"],
                        row["limit_source"],
                    ]
                }
                for row in rows(contexts, impurities, "impurities")
            ],
        ),
        QosSubsection(
            number="2.3.S.4",
            title="Control of Drug Substance",
            mirrors="3.2.S.4",
            values=[_batches_value(contexts, batches)],
            table_caption="Specification",
            table_columns=["Test", "Method", "Acceptance criterion"],
            table_rows=[
                {"cells": [row["test_name"], row["method"], row["acceptance_criterion"]]}
                for row in rows(contexts, specification, "specification")
            ],
        ),
        QosSubsection(
            number="2.3.S.5",
            title="Reference Standards or Materials",
            mirrors="3.2.S.5",
            values=[field(contexts, standards, "standard_statement", "Reference standard")],
        ),
        QosSubsection(
            number="2.3.S.6",
            title="Container Closure System",
            mirrors="3.2.S.6",
            values=[field(contexts, container, "storage_statement", "Container and storage")],
        ),
        QosSubsection(
            number="2.3.S.7",
            title="Stability",
            mirrors="3.2.S.7",
            values=[
                # The claim STATEMENT, not a number of months -- so a retest
                # period the data do not support is as unprintable here as
                # it is in 3.2.S.7.1. See app/templating/stability.py.
                field(contexts, stability, "claim_statement", "Retest period"),
                field(contexts, stability, "storage_statement", "Storage"),
                field(contexts, stability, "tests_monitored", "Attributes monitored"),
            ],
        ),
    ]


def _drug_product_subsections(contexts) -> list[QosSubsection]:
    """2.3.P.1 to 2.3.P.7. Not repeated: there is one medicine."""
    return [
        QosSubsection(
            number="2.3.P.1",
            title="Description and Composition",
            mirrors="3.2.P.1",
            values=[field(contexts, "3.2.P.3.2", "batch_size", "Batch size")],
            table_caption="Composition",
            table_columns=["Component", "Standard", "Per unit (mg)", "Role"],
            table_rows=[
                {
                    "cells": [
                        row["component"],
                        row["spec"],
                        str(row["qty_per_unit_mg"]),
                        row["role"],
                    ]
                }
                for row in rows(contexts, "3.2.P.3.2", "batch_formula")
            ],
        ),
        QosSubsection(
            number="2.3.P.2",
            title="Pharmaceutical Development",
            mirrors="3.2.P.2",
            values=[field(contexts, "3.2.P.2.2", "statement", "Basis")],
            table_caption="Quantity per unit against label claim",
            table_columns=["Active", "Label claim", "Per unit (as base)", "Overage"],
            table_rows=_generic_rows(contexts, "3.2.P.2.2"),
        ),
        QosSubsection(
            number="2.3.P.3",
            title="Manufacture",
            mirrors="3.2.P.3",
            values=[field(contexts, "3.2.P.3.3", "statement", "Process")],
            table_caption="Sites and batch size",
            table_columns=["Item", "Value"],
            table_rows=[
                {"cells": [row["label"], str(row["value"])]}
                for row in rows(contexts, "3.2.P.3.3", "details")
            ],
        ),
        QosSubsection(
            number="2.3.P.4",
            title="Control of Excipients",
            mirrors="3.2.P.4",
            table_caption="Excipients and their standards",
            table_columns=["Excipient", "Function", "Standard", "Grade"],
            table_rows=_generic_rows(contexts, "3.2.P.2.1"),
        ),
        QosSubsection(
            number="2.3.P.5",
            title="Control of Drug Product",
            mirrors="3.2.P.5",
            values=[_batches_value(contexts, "3.2.P.5.4")],
            table_caption="Finished product specification",
            table_columns=["Test", "Method", "Acceptance criterion"],
            table_rows=[
                {"cells": [row["test_name"], row["method"], row["acceptance_criterion"]]}
                for row in rows(contexts, "3.2.P.5.1", "specification")
            ],
        ),
        QosSubsection(
            number="2.3.P.6",
            title="Reference Standards or Materials",
            mirrors="3.2.P.6",
            table_caption="Reference standards",
            table_columns=["Material", "Claimed", "Standard"],
            table_rows=[
                {"cells": [row["material"], row["claimed"], row["standard"]]}
                for row in rows(contexts, "3.2.P.6", "reference_standards")
            ],
        ),
        QosSubsection(
            number="2.3.P.7",
            title="Container Closure System",
            mirrors="3.2.P.7",
            table_caption="Container closure system",
            table_columns=["Component", "Description", "Material", "Artwork"],
            table_rows=_generic_rows(contexts, "3.2.P.2.4"),
        ),
    ]


def _generic_rows(contexts, key: str) -> list[dict]:
    """Rows out of a section that renders the development template's generic
    four-column table (app/templating/development.py `_table`).

    Those contexts hold their rows under `table`, already shaped as
    `{"cells": [...]}` -- so this hands them straight through rather than
    rebuilding them, which is the whole point of deriving: the QOS shows the
    rows 3.2.P.2.2 shows, not a second computation of them.
    """
    table = context_for(contexts, key)["table"]
    return list(table["rows"])
