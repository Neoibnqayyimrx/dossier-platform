"""The sections that describe how the material and the medicine are MADE and
how the formulation was ARRIVED AT (P24d): 3.2.S.2.2-.2.6, 3.2.P.2.1-.2.5,
3.2.P.3.3 and 3.2.P.3.4.

## Why these were left until last

Every one of them is `hybrid` in the target, and they are the most
narrative-led sections in the dossier -- a manufacturing process
description is prose about a process, and no data model of ours contains
it. That made them look like the easy ones ("just a template and a slot"),
which is exactly why they were dangerous to build early: a section that is
ALL slot is a section where a model writes the regulatory content, and the
determinism boundary (AGENTS.md 5) stops meaning anything.

So each one here has a data half that is genuinely derived, and the slot
carries only what is genuinely prose. Where the data half is thin, it is
thin honestly and the docstring says so, rather than being padded out with
values invented to look substantial.

## The regulatory logic worth reading

`_api_coverage` is the one piece of real regulatory reasoning in this
module, and it applies to all four 3.2.S.2 sections. **Where the applicant
claims a CEP or an APIMF/DMF, the manufacturing detail for the drug
substance is not theirs to file.** It lives in the restricted part that the
API manufacturer submits directly to the agency, and the applicant's
section legitimately reduces to a cross-reference. An applicant who instead
writes a full process description they got from a broker is filing
something they cannot support.

So these sections ask what is on file for that substance and say which case
they are in. A CEP number turns 3.2.S.2.2 into a citation; its absence
leaves a narrative slot that has to be filled by someone who knows the
process. The document tells the assessor which of the two they are reading.
"""

from __future__ import annotations

from app.models.enums import PackagingRole
from app.templating.quality_control import MISSING, specification_rows

# Test names that make a specification row a MICROBIOLOGICAL attribute
# (3.2.P.2.5). Matched case-insensitively as substrings, because
# specifications spell these several ways ("Microbial limit test", "Total
# aerobic microbial count", "TAMC").
#
# WHY a vocabulary rather than a flag on SpecificationTest: the flag would
# be a second thing to set correctly on every row, and a row whose name
# says "Microbial limits" while its flag says otherwise is worse than no
# flag. This reads what the filer already wrote. It is deliberately
# generous -- over-listing a row in a development section is a harmless
# inaccuracy, while missing one means the section claims a microbiological
# attribute is uncontrolled when it is not.
_MICROBIOLOGICAL_TERMS = (
    "microb",
    "sterility",
    "endotoxin",
    "pyrogen",
    "tamc",
    "tymc",
    "bioburden",
    "escherichia",
    "salmonella",
    "staphylococcus",
    "pseudomonas",
    "aerobic",
    "yeast",
    "mould",
    "mold",
    "fungal",
)


def _table(columns: list[str], rows: list[list[str]]) -> dict:
    """A table for the shared development template.

    The template has a FIXED four-column table whose headers come from the
    context, so one template serves five sections that each want a
    differently-shaped table. Rows are padded to four cells here rather
    than in the template, because a Jinja index past the end of a list
    raises during render -- and a section that fails to render is a leaf
    missing from the package.

    WHY one padded template rather than five templates: five would be five
    binary files to keep in step for five sections that all say "here is
    what we considered, here is what we chose". The tables genuinely differ
    in their columns and in nothing else.
    """
    if len(columns) > 4:
        raise ValueError(f"The development template has four columns; got {len(columns)}.")
    padded_columns = list(columns) + [""] * (4 - len(columns))
    return {
        "columns": padded_columns,
        "rows": [{"cells": list(row) + [""] * (4 - len(row))} for row in rows],
    }


def _api_coverage(substance) -> tuple[str, bool]:
    """Whether this substance's manufacturing detail is the applicant's to
    file, and the sentence that says so.

    Returns (statement, applicant_must_describe). The boolean is what the
    template uses to decide whether the narrative slot is expected or
    whether its absence is correct -- so an empty slot on a CEP-covered
    section reads as "nothing is owed here" rather than as a gap.
    """
    if substance.cep_number:
        return (
            f"A Certificate of Suitability of the European Pharmacopoeia "
            f"(CEP {substance.cep_number}) is claimed for {substance.inn_name}. The "
            f"manufacturing detail is covered by the certificate and its supporting "
            f"dossier held by the European Directorate for the Quality of Medicines; "
            f"the certificate is filed at 1.2.15. This section is a cross-reference, "
            f"not an independent description.",
            False,
        )
    if substance.dmf_number:
        return (
            f"An Active Pharmaceutical Ingredient Master File (DMF/APIMF "
            f"{substance.dmf_number}) is claimed for {substance.inn_name}. The restricted "
            f"part is submitted to the authority by the API manufacturer; the letter of "
            f"access is filed at 1.2.16. This section covers the open part only.",
            False,
        )
    return (
        f"No CEP and no APIMF are claimed for {substance.inn_name}, so the applicant "
        f"files this section in full.",
        True,
    )


def _substance_details(substance) -> list[dict[str, str]]:
    manufacturer = substance.manufacturer
    rows = [
        ("Drug substance", substance.inn_name),
        ("Manufacturer", manufacturer.name if manufacturer is not None else MISSING),
        (
            "Site address",
            manufacturer.site_address if manufacturer is not None else MISSING,
        ),
        (
            "Compendial standard",
            substance.compendial_std.value if substance.compendial_std else MISSING,
        ),
        ("CEP number", substance.cep_number or "None claimed"),
        ("DMF / APIMF number", substance.dmf_number or "None claimed"),
    ]
    return [{"label": label, "value": value or MISSING} for label, value in rows]


def drug_substance_manufacture_context(section, substance, narrative) -> dict:
    """3.2.S.2.2, 3.2.S.2.3, 3.2.S.2.4 and 3.2.S.2.6 -- one shape, four
    sections, one per drug substance.

    They share a template for the same reason 3.2.S.4.1 and 3.2.P.5.1 do:
    they are four questions asked of the same material, each answered by
    the same identity block plus one paragraph. Four templates would be
    four places for that identity block to be laid out differently.
    """
    statement, applicant_must_describe = _api_coverage(substance)
    return {
        "section_number": section.number,
        "section_title": section.title,
        "substance": substance,
        "coverage_statement": statement,
        "applicant_must_describe": applicant_must_describe,
        "details": _substance_details(substance),
        "narrative": narrative,
    }


# ---- 3.2.P.2: pharmaceutical development -----------------------------------


def components_context(section, project, narrative) -> dict:
    """3.2.P.2.1 -- the components of the drug product.

    Covers 3.2.P.2.1.1 (drug substance) and 3.2.P.2.1.2 (excipients) in one
    document, as the target declares. The table is the actives and the
    excipients TOGETHER, because the question this section answers is about
    the two in combination -- which is also what the narrative slot is for:
    drug-excipient compatibility is a judgement supported by data filed
    elsewhere, and it is genuinely the applicant's to write.
    """
    product = project.product
    rows: list[list[str]] = []
    for api in product.apis:
        rows.append(
            [
                api.inn_name,
                "Active",
                api.compendial_std.value if api.compendial_std else MISSING,
                api.salt_form or "—",
            ]
        )
    for excipient in product.excipients:
        rows.append(
            [
                excipient.name,
                excipient.function.value if excipient.function else MISSING,
                (excipient.compendial_status.value if excipient.compendial_status else MISSING),
                excipient.grade or "—",
            ]
        )
    return {
        "section_number": section.number,
        "section_title": section.title,
        "statement": (
            "The components below are those filed in the composition (3.2.P.1) and the "
            "batch formula (3.2.P.3.2). Their specifications are filed at 3.2.S.4.1 for "
            "the actives and 3.2.P.4.1 for the excipients."
        ),
        "details": [],
        "table_caption": "Components of the drug product",
        "table": _table(["Component", "Function", "Standard claimed", "Grade / salt form"], rows),
        "narrative": narrative,
    }


def formulation_context(section, project, narrative) -> dict:
    """3.2.P.2.2 -- formulation development, OVERAGES, and physicochemical
    properties.

    The overage column is the reason this section is worth generating
    rather than writing. An overage is the difference between what the
    formula puts in and what the label claims, and it is a thing a
    regulator asks about specifically -- ICH Q8 requires it to be justified,
    and an unjustified one reads as a potency problem being managed rather
    than solved.

    It is COMPUTED here from the batch formula and the declared strength,
    never typed. That is the same relationship rule R04 checks from the
    other end: R04 asks whether the BATCH adds up, this asks whether the
    UNIT does.

    **The salt factor does not belong in this calculation, and getting that
    wrong is easy.** `BatchFormulaLine.qty_per_unit_mg` holds the BASE
    quantity per unit -- R04 multiplies it by the salt factor itself to
    reach the weighed batch quantity, which is why its own comment reads
    "per-unit base mg". The declared strength is also stated as base. So an
    overage is base against base, and folding the salt factor in here
    reported a -12.9 % overage for an amoxicillin trihydrate line that has
    none: the arithmetic was comparing 500 mg of base against 574 mg of
    trihydrate and calling the difference a formulation decision.
    """
    product = project.product
    rows: list[list[str]] = []
    for line in product.batch_formula:
        if not line.is_active:
            continue
        api = line.active_ingredient
        if api is None and len(product.apis) == 1:
            # A single-active product's one active line is unambiguous --
            # the same allowance rule R04 makes, and for the same reason.
            api = product.apis[0]
        if api is None or api.strength_value is None:
            rows.append([line.component, MISSING, f"{float(line.qty_per_unit_mg):g} mg", MISSING])
            continue
        label_claim = float(api.strength_value)
        actual = float(line.qty_per_unit_mg)
        overage = (actual - label_claim) / label_claim * 100 if label_claim else 0.0
        rows.append(
            [
                line.component,
                f"{label_claim:g} {api.strength_unit or ''}".strip(),
                f"{actual:g} mg",
                # "None" rather than "0.0 %": an overage of nothing is the
                # ordinary case and should read as a plain answer, not as a
                # number an assessor has to interpret. The 0.05 % threshold
                # is rounding tolerance, not a regulatory allowance.
                "None" if abs(overage) < 0.05 else f"{overage:+.1f} %",
            ]
        )

    properties = [
        {"label": f"{api.inn_name} — particle size", "value": api.particle_size}
        for api in product.apis
        if api.particle_size
    ]
    properties += [
        {"label": f"{api.inn_name} — residual solvents", "value": api.residual_solvents}
        for api in product.apis
        if api.residual_solvents
    ]

    return {
        "section_number": section.number,
        "section_title": section.title,
        "statement": (
            "Quantities are those filed in the batch formula (3.2.P.3.2). The overage "
            "column is computed from the quantity per unit against the declared strength "
            "and salt factor; it is not separately entered, so it cannot disagree with "
            "the formula."
        ),
        "details": properties,
        "table_caption": "Quantity per unit against label claim",
        "table": _table(
            # "as base" in the column heading, because that is what the
            # figure IS -- a reader who assumes it is the weighed quantity
            # would read every salt-form line as under-formulated.
            ["Active", "Label claim", "Quantity per unit (as base)", "Overage"],
            rows,
        ),
        "narrative": narrative,
    }


def process_development_context(section, project, narrative) -> dict:
    """3.2.P.2.3 -- manufacturing process development.

    The data half is the sites and the batches actually filed, with their
    stated purpose. That is a genuinely useful frame for the narrative: a
    development section is an account of how the process reached the scale
    and the equipment the filed batches were made on, and an assessor reads
    the two together.
    """
    product = project.product
    sites = [m for m in product.manufacturers if m.role is not None]
    batches = sorted(product.batch_analyses, key=lambda b: b.batch_number)
    rows = [
        [
            batch.batch_number,
            batch.batch_size or MISSING,
            batch.manufacturer.name if batch.manufacturer else MISSING,
            batch.purpose or MISSING,
        ]
        for batch in batches
    ]
    return {
        "section_number": section.number,
        "section_title": section.title,
        "statement": (
            "The batches below are those filed at 3.2.P.5.4. Development of the process "
            "is described against the scale and the sites they were made at."
        ),
        "details": [
            {"label": site.name, "value": f"{site.role.value} — {site.country or MISSING}"}
            for site in sites
        ],
        "table_caption": "Batches filed",
        "table": _table(["Batch", "Size", "Site", "Purpose"], rows),
        "narrative": narrative,
    }


def container_development_context(section, project, narrative) -> dict:
    """3.2.P.2.4 -- the container closure system, as a development question.

    The SAME packs 3.2.P.7 files, filtered the same way (drug-substance
    packaging excluded by role, as rule R12 and 3.2.P.7's expansion do). The
    difference between this section and 3.2.P.7 is not the data, it is the
    question: 3.2.P.7 says what the pack IS, and this says why it is
    suitable -- which is the narrative slot, supported by the stability
    data filed at 3.2.P.8.3 in that same pack.
    """
    packs = [
        pack for pack in project.product.packaging if pack.role is not PackagingRole.DRUG_SUBSTANCE
    ]
    rows = [
        [
            pack.component.value,
            pack.description,
            pack.material or MISSING,
            pack.artwork_ref or "—",
        ]
        for pack in packs
    ]
    return {
        "section_number": section.number,
        "section_title": section.title,
        "statement": (
            "These are the packs filed at 3.2.P.7. Suitability is supported by the "
            "stability data generated in this container closure system (3.2.P.8.3)."
        ),
        "details": [],
        "table_caption": "Container closure system",
        "table": _table(["Component", "Description", "Material", "Artwork"], rows),
        "narrative": narrative,
    }


def microbiological_context(section, project, narrative) -> dict:
    """3.2.P.2.5 -- microbiological attributes.

    The data half is which of the FINISHED PRODUCT's own specification rows
    are microbiological -- read from 3.2.P.5.1 rather than restated, so a
    test added to the specification appears here without anybody
    remembering to add it.

    WHY an empty table does not print "no microbiological attributes apply":
    that sentence is a regulatory CLAIM, and a correct one for many
    non-sterile solid oral dosage forms -- but it is the applicant's claim
    to make, not an inference from an empty list. An empty specification of
    a sterile product would produce exactly the same emptiness, and the
    document would then assert the opposite of the truth. So the section
    says what is specified, and the narrative slot carries the position.
    """
    rows = [
        [row.test_name, row.method, row.acceptance_criterion, ""]
        for row in specification_rows(project.product)
        if any(term in row.test_name.lower() for term in _MICROBIOLOGICAL_TERMS)
    ]
    return {
        "section_number": section.number,
        "section_title": section.title,
        "statement": (
            "The rows below are the microbiological tests in the finished product "
            "specification (3.2.P.5.1)."
            if rows
            else (
                "No test in the finished product specification (3.2.P.5.1) was identified "
                "as a microbiological attribute. Whether that is correct for this dosage "
                "form is stated below."
            )
        ),
        "details": [],
        "table_caption": "Microbiological attributes specified",
        "table": _table(["Test", "Method", "Acceptance criterion"], rows),
        "narrative": narrative,
    }


# ---- 3.2.P.3.3 / 3.2.P.3.4: making the drug product ------------------------


def drug_product_manufacture_context(section, project, narrative) -> dict:
    """3.2.P.3.3 (process description) and 3.2.P.3.4 (critical steps).

    **The thinnest data half in the platform, and deliberately not padded.**
    A manufacturing process description is a description of a process, and
    the in-process controls of 3.2.P.3.4 are limits nothing in this data
    model holds. Inventing an in-process control table to make the section
    look generated would be manufacturing regulatory data, which is the one
    thing this platform must never do.

    What IS derived is the frame an assessor needs to read the prose
    against: which sites make it, at what batch size, and the composition
    the process has to deliver. Those three are already filed at 3.2.P.3.1,
    3.2.P.3.2 and 3.2.P.1, and repeating them here from their own sources
    means this section cannot describe a process for a batch size the
    formula does not state.
    """
    product = project.product
    lines = list(product.batch_formula)
    sizes = {line.batch_size_units for line in lines}
    batch_size = f"{sizes.pop():,} units" if len(sizes) == 1 else MISSING
    sites = [
        m
        for m in product.manufacturers
        if m.role is not None and m.role.value != "api-manufacturer"
    ]
    return {
        "section_number": section.number,
        "section_title": section.title,
        "statement": (
            "The process described below produces the composition filed at 3.2.P.1, at "
            "the batch size filed at 3.2.P.3.2, at the sites filed at 3.2.P.3.1. The "
            "executed batch record is filed under regional information (3.2.R)."
        ),
        "details": [
            {"label": "Batch size", "value": batch_size},
            *[{"label": site.name, "value": site.role.value} for site in sites],
        ],
        "table_caption": "Composition the process must deliver",
        "table": _table(
            ["Component", "Standard", "Quantity per unit (mg)", "Role"],
            [
                [
                    line.component,
                    line.spec,
                    f"{float(line.qty_per_unit_mg):g}",
                    "Active" if line.is_active else "Excipient",
                ]
                for line in lines
            ],
        ),
        "narrative": narrative,
    }
