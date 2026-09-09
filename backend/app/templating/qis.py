"""The Quality Information Summary, leaf 1.4.2 (P24b).

## What the document is

The QIS is NAFDAC's (and the WHO prequalification programme's) structured
summary of the quality dossier: a form, filled field by field, restating
Module 3 in the agency's own layout so an assessor can read the whole of
the quality case in a dozen pages before opening the body of data.

## Why it is the highest-leverage document in the target

The target TOC says so in its own note on this leaf, and the reason is
arithmetic rather than rhetorical. A QIS has on the order of a hundred
fields, every one of which already exists in Module 3. Filled by hand it is
a hundred opportunities for a transcription error, and the errors are
systematically the WORST kind: a QIS field is what an assessor reads
FIRST, so a wrong limit there is a wrong limit acted upon. Then Module 3 is
revised during review and the form is not, and the two disagree in a
submission whose whole purpose was to be consistent.

Here it has no fields of its own at all. Every value is pulled through
`app.templating.derived` out of the very context dict the corresponding
Module 3 section renders from -- so "keeping the QIS in step with Module 3"
is not a task anybody has to do or remember. There is one value and two
documents printing it.

## Structure

Three parts, following the source dossier's own QIS:

  Part 1  general product information   -- what is being registered
  Part 2  drug substance, per active    -- 3.2.S, one block per substance
  Part 3  drug product                  -- 3.2.P

Part 2 repeats **inside one document** rather than expanding into several
leaves. That is the opposite call from 3.2.S itself (which repeats per
substance as separate leaves, see app/templating/instances.py) and it is
the right one for the same reason: 3.2.S is a body of data about ONE
material, while a QIS is a single form describing ONE APPLICATION. An
agency expecting one form and receiving two would treat the second as a
duplicate filing.

## No narrative slots

Deliberate, and the same call 1.4.1 (the BTI form) made. A form an agency
reads field-by-field has no place for a drafted paragraph, and a slot here
could only introduce a claim that Module 3 does not make -- which is
precisely the divergence the document is built to eliminate.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.templating.derived import SourcedValue, context_for, field, rows, section_contexts
from app.templating.instances import expand_sections


@dataclass(frozen=True)
class SubstanceBlock:
    """Part 2 of the QIS, for one active ingredient.

    Every row inside carries the instance key of the 3.2.S leaf it came
    from, printed in the rendered form as the cross-reference: an assessor
    querying a value in the QIS should be able to find the leaf that
    justifies it without asking.
    """

    name: str
    identity: list[SourcedValue]
    specification: list
    impurities: list
    stability: list[SourcedValue]


def qis_context(section, project) -> dict:
    """1.4.2, assembled entirely out of Module 3's own rendered contexts."""
    contexts = section_contexts(project)

    substances = [
        _substance_block(contexts, instance)
        for instance in expand_sections(project)
        if instance.number == "3.2.S.1"
    ]

    return {
        "section_number": section.number,
        "section_title": section.title,
        "product_name": project.product.brand_name,
        "general": _general(contexts, project),
        "substances": substances,
        "composition": rows(contexts, "3.2.P.3.2", "batch_formula"),
        "product_specification": rows(contexts, "3.2.P.5.1", "specification"),
        "batches": rows(contexts, "3.2.P.5.4", "batches"),
        "product_stability": _product_stability(contexts),
        "container": _container(contexts),
        # Printed at the foot of the form. WHY the document says this out
        # loud rather than only the code knowing it: a filer who believes a
        # field here is editable will look for the place to edit it, and an
        # assessor who knows the form is derived reads a discrepancy
        # between it and Module 3 as a platform bug rather than as an
        # applicant's inconsistency. Both readings are worth having.
        "derivation_note": (
            "Every field in this summary is rendered from the same data as the Module 3 "
            "section named beside it. No field of this form is separately entered, so it "
            "cannot state a value that Module 3 does not."
        ),
    }


def _general(contexts, project) -> list[SourcedValue]:
    """Part 1: what is being registered.

    Note where these come from. The product's identity is read out of
    3.2.P.1's context -- the section that DESCRIBES the drug product --
    rather than off `project.product`, even though the object is the same
    one. Reading it from the section is what keeps the rule true without
    exception: no field of this form has a source other than a Module 3
    leaf, so there is no case to argue about later.
    """
    described = context_for(contexts, "3.2.P.1")["product"]
    return [
        SourcedValue("Product name", described.brand_name, "3.2.P.1"),
        SourcedValue(
            "Active ingredient(s)",
            ", ".join(api.inn_name for api in described.apis) or "[[NOT YET ON FILE]]",
            "3.2.P.1",
        ),
        # `strength_display`, never a `strength` field -- there isn't one,
        # deliberately (app/models/product.py): a combination product has
        # one strength PER ACTIVE, and a QIS field that could hold only one
        # of them would misstate every fixed-dose combination.
        SourcedValue("Strength", described.strength_display, "3.2.P.1"),
        SourcedValue(
            "Dosage form",
            described.dosage_form.value if described.dosage_form else "[[NOT YET ON FILE]]",
            "3.2.P.1",
        ),
        SourcedValue(
            "Route of administration",
            described.route_of_administration or "[[NOT YET ON FILE]]",
            "3.2.P.1",
        ),
        field(contexts, "3.2.P.3.2", "batch_size", "Batch size"),
        SourcedValue("Applicant", _applicant_name(project), "1.2.2"),
    ]


def _applicant_name(project) -> str:
    """The one field on the form that is NOT derived from Module 3, and it
    is worth being explicit about why.

    Who is applying is not a quality fact -- it appears nowhere in the body
    of data, because Module 3 describes a medicine and not a company. Its
    source is the application form (1.2.2), which is where it is entered
    once and from which the cover letter and the registration form also
    read. So the rule "no QIS field is separately entered" holds; the
    source for this one is a Module 1 leaf, and the form says so.
    """
    applicant = project.applicant
    return applicant.company_name if applicant is not None else "[[NOT YET ON FILE]]"


def _substance_block(contexts, instance) -> SubstanceBlock:
    """Part 2, for one active. Every row comes from that substance's own
    3.2.S leaves -- never from "the drug substance", which a combination
    product does not have."""
    slug = instance.subject_slug
    general_key = f"3.2.S.1-{slug}"
    specification_key = f"3.2.S.4.1-{slug}"
    impurities_key = f"3.2.S.3.2-{slug}"
    stability_key = f"3.2.S.7.1-{slug}"

    return SubstanceBlock(
        name=instance.subject.inn_name,
        identity=[
            SourcedValue(row["label"], str(row["value"]), general_key)
            for row in rows(contexts, general_key, "nomenclature")
        ],
        specification=rows(contexts, specification_key, "specification"),
        impurities=rows(contexts, impurities_key, "impurities"),
        stability=[
            field(contexts, stability_key, "claim_statement", "Retest period"),
            field(contexts, stability_key, "storage_statement", "Storage"),
        ],
    )


def _product_stability(contexts) -> list[SourcedValue]:
    """Part 3's shelf-life block.

    The claim statement, not a bare number of months, and that is the
    important part. 3.2.P.8.1 REFUSES to print a claimed shelf life the
    long-term data do not reach -- it prints a marker naming both figures
    instead (see app/templating/stability.py `_claim_statement`). Because
    this field is that same string, an unsupported claim is unprintable
    here too. A QIS with its own `shelf_life_months` lookup would happily
    print the claim the data disproves, on the first page an assessor
    reads.
    """
    return [
        field(contexts, "3.2.P.8.1", "claim_statement", "Shelf life"),
        field(contexts, "3.2.P.8.1", "storage_statement", "Storage conditions"),
        field(contexts, "3.2.P.8.1", "tests_monitored", "Attributes monitored on stability"),
    ]


def _container(contexts) -> list[SourcedValue]:
    """The container closure system, from whichever 3.2.P.7 leaves exist.

    3.2.P.7 repeats per pack, so there is no single context to read -- the
    QIS prints one line per pack, each naming its own leaf. Built by
    scanning the contexts rather than re-expanding the packs, because
    re-expanding would be a second walk over the same collection and could
    (after some future change to the pack axis) disagree with the first.
    """
    lines: list[SourcedValue] = []
    for key in sorted(contexts):
        if not key.startswith("3.2.P.7"):
            continue
        pack = contexts[key]["pack"]
        lines.append(
            SourcedValue(
                label=pack.component.value,
                value=pack.description,
                source=key,
            )
        )
    if not lines:
        lines.append(
            SourcedValue(
                label="Container closure system",
                value="[[NO DRUG PRODUCT PACKAGING ON FILE -- 3.2.P.7 is empty]]",
                source="3.2.P.7",
            )
        )
    return lines
