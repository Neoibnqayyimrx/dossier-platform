"""Context builders for the control sections (P20): 3.2.S.3.2, 3.2.S.4.x,
3.2.P.4.x, 3.2.P.5.x.

WHY these live in their own module rather than as eleven more branches in
context.py: they are eleven sections built from FOUR shapes -- a
specification table, a batch table, an impurity table, and a narrative with
one of those tables under it. Written as branches they would be eleven
near-copies; written as four builders parameterised by their owner they are
the same generalisation the model layer made, one level up.

The organising idea, and it is the phase's whole thesis:

    A specification is one artifact. The CTD asks for it of the drug
    substance (3.2.S.4.1), of each excipient (3.2.P.4.1) and of the
    finished product (3.2.P.5.1). One model, one editor, one renderer, one
    set of rules -- because the failure mode of three of each is that they
    disagree, and disagreement between sections of one dossier is the
    defect this platform exists to remove.

Everything here is synchronous, DB-free and Word-library-free, exactly like
context.py -- these functions take already-loaded ORM objects and return a
plain dict.
"""

from __future__ import annotations

from app.models.enums import SpecificationOwnerKind

MISSING = "[[NOT YET ON FILE]]"

# Section number -> the human label for whatever owns its specification.
# One table rather than a conditional per builder: every one of these
# sections needs to print "Drug substance: X" or "Excipient: Y" at the top,
# and an assessor reading two of them side by side must not find the same
# owner described two different ways.
OWNER_LABEL: dict[SpecificationOwnerKind, str] = {
    SpecificationOwnerKind.DRUG_SUBSTANCE: "Drug substance",
    SpecificationOwnerKind.DRUG_PRODUCT: "Drug product",
    SpecificationOwnerKind.EXCIPIENT: "Excipient",
}


def owner_name(owner) -> str:
    """What an owner is called. Each of the three spells its name
    differently (`inn_name`, `brand_name`, `name`), and every caller here
    was otherwise about to write the same three-branch expression."""
    for attribute in ("inn_name", "brand_name", "name"):
        value = getattr(owner, attribute, None)
        if value:
            return str(value)
    return MISSING


def compendial_standard(owner) -> str:
    """The standard the material is claimed against, however its own model
    spells the field. A drug substance has `compendial_std`, an excipient
    has `compendial_status`, and the finished product has neither -- a
    medicine is not controlled against a monograph, its ingredients are, so
    the honest answer for 3.2.P.5.1 is that this is an in-house
    specification unless a monograph for the finished dosage form exists.
    """
    for attribute in ("compendial_std", "compendial_status"):
        value = getattr(owner, attribute, None)
        if value is not None:
            return value.value
    return "In-house (finished product)"


def specification_rows(owner) -> list:
    """The owner's specification tests, in the order the applicant chose.

    Sorted here rather than relied on from the relationship's `order_by`:
    that ordering only applies when the rows are loaded FROM THE DATABASE,
    so an object built in memory -- a seed, a test, an API create before the
    flush -- would render in insertion order. The rendered table has to be
    deterministic either way, because the builders must be byte-identical
    across runs (AGENTS.md §5). This is the same trap P13 documented for
    3.2.S.4.1; it applies unchanged to the two new owners.
    """
    return sorted(owner.specification, key=lambda row: row.sort_order)


def specification_context(section, owner) -> dict:
    """3.2.S.4.1 / 3.2.P.4.1 / 3.2.P.5.1 -- the same page, three owners."""
    return {
        "section_number": section.number,
        "section_title": section.title,
        "owner_label": OWNER_LABEL[_owner_kind_of(owner)],
        "owner_name": owner_name(owner),
        "compendial_standard": compendial_standard(owner),
        "specification": [
            {
                "test_name": row.test_name,
                "method": row.method,
                "acceptance_criterion": row.acceptance_criterion,
            }
            for row in specification_rows(owner)
        ],
    }


def analytical_procedures_context(section, owners, narrative) -> dict:
    """3.2.S.4.2 / 3.2.P.4.2 / 3.2.P.5.2.

    The regulatory point, and the reason this is `hybrid` rather than
    `generated`: **where the specification is pharmacopoeial, an analytical
    procedure reduces to a citation of the monograph; where it is in-house,
    it needs a full description.** Both cases occur in one table -- a BP
    assay alongside an in-house related-substances method is completely
    ordinary -- so the section cannot be all-citation or all-prose.

    So the table is generated (every row already carries its method as a
    citation, which is what a pharmacopoeial row needs and all it needs)
    and the narrative slot carries the descriptions the in-house rows owe.
    The context also tells the template WHICH rows those are, so the prose
    has something to be checked against rather than being a free essay.

    `owners` is a list because 3.2.P.4.2 covers every excipient in one
    document -- the target TOC declares no repeat axis for it, unlike
    3.2.P.4.1. One document listing each excipient's methods is what an
    assessor wants there; one document per excipient would be a folder of
    one-line files.
    """
    rows = []
    in_house = []
    for owner in owners:
        label = owner_name(owner)
        for row in specification_rows(owner):
            compendial = _is_compendial_method(row.method)
            rows.append(
                {
                    "owner": label,
                    "test_name": row.test_name,
                    "method": row.method,
                    "basis": "Compendial" if compendial else "In-house",
                }
            )
            if not compendial:
                in_house.append(f"{label}: {row.test_name} ({row.method})")

    return {
        "section_number": section.number,
        "section_title": section.title,
        "procedures": rows,
        # Named explicitly rather than left for the reader to spot: these
        # are the rows whose validation reports 3.2.S.4.3 / 3.2.P.5.3 must
        # exist for. A compendial method's validation is the
        # pharmacopoeia's; an in-house one's is the applicant's.
        "in_house_statement": (
            "The following procedures are in-house and are described below; their "
            "validation is filed in the corresponding validation section: " + "; ".join(in_house)
            if in_house
            else (
                "All analytical procedures used are those of the cited pharmacopoeial "
                "monographs. No in-house method is used, so no method description is "
                "reproduced here -- monograph text is copyrighted and is cited, never "
                "copied."
            )
        ),
        "narrative": narrative,
    }


def justification_context(section, owners, narrative) -> dict:
    """3.2.P.4.4 / 3.2.P.5.6 -- justification of the specification.

    Genuinely `hybrid`: the justification of a limit is an argument, which
    is prose, but the limits being justified are data and must be the SAME
    data the specification section renders. Printing the table here means
    the prose is read against the actual limits rather than against a typed
    restatement of them -- which is how a justification comes to defend a
    limit the specification no longer contains.
    """
    rows = [
        {
            "owner": owner_name(owner),
            "test_name": row.test_name,
            "acceptance_criterion": row.acceptance_criterion,
            "basis": (
                f"{compendial_standard(owner)} monograph"
                if _is_compendial_method(row.method)
                else "In-house limit -- justified below"
            ),
        }
        for owner in owners
        for row in specification_rows(owner)
    ]
    return {
        "section_number": section.number,
        "section_title": section.title,
        "limits": rows,
        "narrative": narrative,
    }


def batch_analysis_context(section, owner) -> dict:
    """3.2.S.4.4 / 3.2.P.5.4 -- what the batches actually gave.

    Two tables. First the batches themselves (number, date, size, site,
    purpose), because an assessor's first question is which material these
    numbers describe. Then the results, **one row per test per batch, with
    that test's acceptance criterion on the same line as the result**.

    WHY that layout and not the matrix a certificate of analysis uses (one
    row per test, one column per batch): a matrix needs as many columns as
    there are batches, and a docxtpl column loop (`{%tc %}`) has the same
    "the tag needs a cell of its own" constraint that `{%tr %}` has for
    rows -- which P13's build-log entry already recorded as the trap that
    dies with "Encountered unknown tag 'endfor'". Nesting a per-row column
    loop inside a row loop compounds it.

    The flat form is also the better document, which is the honest reason
    to prefer it. What must never happen is a limit printed in one table
    and the numbers judged against it printed in another -- that is the
    layout that lets an out-of-specification result pass unnoticed. One row
    carrying test, limit, batch and result puts them a centimetre apart on
    every single line, for any number of batches.

    Every cell is looked up through the RESULT's own
    `specification_test_id`, never by matching test names between the two
    tables. A name match would silently produce a blank row when a test is
    renamed; the foreign key cannot.
    """
    batches = sorted(owner.batch_analyses, key=lambda b: b.batch_number)
    tests = specification_rows(owner)

    results_by_batch = {
        batch.id: {result.specification_test_id: result for result in batch.results}
        for batch in batches
    }

    rows = []
    for test in tests:
        for batch in batches:
            result = results_by_batch[batch.id].get(test.id)
            rows.append(
                {
                    "test_name": test.test_name,
                    "acceptance_criterion": test.acceptance_criterion,
                    "batch_number": batch.batch_number,
                    # "Not tested" rather than an empty cell: a blank is
                    # ambiguous between "not tested" and "we forgot to type
                    # it", and an assessor reading a blank writes a question
                    # either way. Saying it makes the gap the applicant's
                    # declared position.
                    "result": result.result if result is not None else "Not tested",
                }
            )

    return {
        "section_number": section.number,
        "section_title": section.title,
        "owner_label": OWNER_LABEL[_owner_kind_of(owner)],
        "owner_name": owner_name(owner),
        "batches": [
            {
                "batch_number": batch.batch_number,
                "manufacture_date": (
                    batch.manufacture_date.isoformat() if batch.manufacture_date else MISSING
                ),
                "batch_size": batch.batch_size or MISSING,
                "site": batch.manufacturer.name if batch.manufacturer else MISSING,
                "purpose": batch.purpose or MISSING,
            }
            for batch in batches
        ],
        "results": rows,
        "no_batches_statement": (
            ""
            if batches
            else (
                f"[[NO BATCH ANALYSIS ON FILE for {owner_name(owner)} -- "
                f"{section.number} cannot be completed]]"
            )
        ),
    }


def impurities_context(section, owner) -> dict:
    """3.2.S.3.2 / 3.2.P.5.5 -- the named impurity profile.

    `limit_source` is rendered as its own column rather than folded into
    the limit, because an uncited limit is the query an assessor writes
    back. A limit with a stated basis -- a monograph, an ICH Q3A/Q3B
    threshold, a toxicological justification -- is a commitment that can be
    traced; a bare number is a number.
    """
    impurities = sorted(owner.impurities, key=lambda i: (i.impurity_type.value, i.name))
    return {
        "section_number": section.number,
        "section_title": section.title,
        "owner_label": OWNER_LABEL[_owner_kind_of(owner)],
        "owner_name": owner_name(owner),
        "impurities": [
            {
                "name": impurity.name,
                "impurity_type": impurity.impurity_type.value,
                "limit": impurity.limit or MISSING,
                "limit_source": impurity.limit_source or "[[NO SOURCE CITED]]",
                "origin": impurity.origin or MISSING,
            }
            for impurity in impurities
        ],
        "no_impurities_statement": (
            ""
            if impurities
            else (
                f"[[NO IMPURITIES ON FILE for {owner_name(owner)} -- "
                f"{section.number} cannot be completed]]"
            )
        ),
    }


# ---- helpers ---------------------------------------------------------------


def _owner_kind_of(owner) -> SpecificationOwnerKind:
    """Which of the three an owner OBJECT is.

    Deliberately duck-typed on a field each model uniquely has rather than
    imported and isinstance-checked: this module, like context.py, stays
    free of a hard model import so the templating layer never depends on
    the ORM's class identities.
    """
    if hasattr(owner, "inn_name"):
        return SpecificationOwnerKind.DRUG_SUBSTANCE
    if hasattr(owner, "brand_name"):
        return SpecificationOwnerKind.DRUG_PRODUCT
    return SpecificationOwnerKind.EXCIPIENT


# Method citations that name a pharmacopoeia. Substring matching on
# purpose: the field is a free-text CITATION ("HPLC, BP monograph",
# "USP <467>", "Ph. Eur. 2.9.40"), and demanding a controlled vocabulary
# would either reject real citations or push the filer into a dropdown that
# cannot express "BP monograph, method B".
#
# The failure direction matters. A false NEGATIVE (a compendial method read
# as in-house) asks for a description that is already public -- wasteful,
# harmless. A false POSITIVE (an in-house method read as compendial) would
# tell the applicant they owe no method description when they do, which is
# a deficiency letter. So the list stays narrow: only tokens that can only
# mean a pharmacopoeia.
_COMPENDIAL_TOKENS = ("monograph", " bp", "bp ", "usp", "ph. eur", "ph eur", "ep ", " jp", "ich ")


def _is_compendial_method(method: str) -> bool:
    text = f" {method.lower()} "
    return any(token in text for token in _COMPENDIAL_TOKENS)
