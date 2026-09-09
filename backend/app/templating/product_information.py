"""Context builders for 1.3.1, 1.3.2 and 1.3.3 -- and the one function that
makes them unable to disagree (P23).

## Read this part first

`shared_values(product)` computes every fact that appears in MORE THAN ONE
of the three product-information documents. All three context builders
below call it. Nothing else in this module recomputes any of those values,
and no column anywhere stores a second copy of one.

That is the whole mechanism. The Summary of Product Characteristics, the
label and the leaflet contradicting each other on shelf life or storage or
pack size is one of the most commonly raised deficiencies in real filings,
and it is not caused by disagreement -- it is caused by there being three
copies of the number. Here there is one expression of it, evaluated once
per render.

Rule R31 asks the three finished contexts whether they agree anyway. It
cannot fire while this module is shaped like this, which is exactly what it
is for: the day someone adds a `shelf_life_months` column to
ProductInformation "just for the label", validation fails before an
assessor does. A test (`test_none_of_the_three_can_be_made_to_disagree`)
holds the same line from the other side.

## Provenance is a field, not a comment

Every `SharedValue` carries `source`: a sentence naming where the value
came from, in the filer's own vocabulary ("your stability data", "step 1 of
the wizard"). It is printed in the wizard beside the read-only field and in
the three-way comparison view, because "this is derived" is useless
information unless it also says *derived from what*. A filer who cannot see
that the shelf life comes from the stability study will keep trying to
type it.

## Where the LLM is allowed in

The label has no narrative slots at all -- it is short and entirely
factual, and there is nothing on it a model could add that would not be a
regulatory claim.

The SmPC's slots are its 5.x sections (pharmacodynamic, pharmacokinetic and
preclinical properties): for a multisource product these are
literature-derived description, which is what the knowledge base is for.
Its 4.x clinical particulars are NOT slots -- see app/models/
product_information.py on why an invented indication is the one error the
existing guardrails cannot catch.

The leaflet's slots re-say the same facts in plain language. That is a
rewriting task with a source to check against, and it is judged in the
PATIENT register (app/narrative/guardrails.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import (
    AdverseEventFrequency,
    PackagingComponent,
    PackagingRole,
    StabilityStudyType,
)
from app.models.stability import supported_months

# What a document prints where a shared fact should be but is not. The same
# marker the rest of the templating layer uses (app.templating.context.
# MISSING) -- imported rather than retyped, because it is the string a
# reader scans a rendered section for.
from app.templating.quality_control import MISSING

# The order every SmPC and every leaflet prints adverse effects in. Defined
# by the frequency bands themselves, so it is read off the enum rather than
# typed: adding a band to `AdverseEventFrequency` puts it in the right place
# in both documents with no further edit.
_FREQUENCY_ORDER = {frequency.value: index for index, frequency in enumerate(AdverseEventFrequency)}

# The pack components that describe the finished product to a patient. A
# drug-substance drum is excluded by role below; these two are what
# "nature and contents of container" (SmPC 6.5) means.
_CONTAINER_COMPONENTS = (PackagingComponent.PRIMARY, PackagingComponent.SECONDARY)


@dataclass(frozen=True)
class SharedValue:
    """One fact that more than one of the three documents prints.

    `field` is the machine key the three contexts and the comparison view
    agree on. `smpc_section` is the numbered SmPC section it appears in,
    which is how a pharmacist finds it -- an assessor reading a query about
    "6.4" needs the storage statement, not a field called `storage`.
    """

    field: str
    label: str
    value: str
    source: str
    smpc_section: str | None = None


def _container_rows(product) -> list[dict[str, str]]:
    """The finished product's packs, as the container section renders them.

    Drug-substance packaging is excluded the same way rule R12 and
    3.2.P.7's expansion exclude it: an API drum is not where the medicine's
    pack size is printed. The negative test on `role` is deliberate and its
    reasoning is `app.templating.instances._drug_product_packs`' -- a pack
    built in memory and not yet flushed still has `role is None`, and
    asking `is DRUG_PRODUCT` would silently empty this list.
    """
    return [
        {
            "component": pack.component.value,
            "description": pack.description,
            "material": pack.material or "",
        }
        for pack in product.packaging
        if pack.role is not PackagingRole.DRUG_SUBSTANCE and pack.component in _CONTAINER_COMPONENTS
    ]


def container_statement(product) -> str:
    """SmPC 6.5 / the label's pack statement, as one sentence.

    The declared pack size leads it, because that is the number a patient
    counts and an assessor cross-checks against the artwork (rule R12).
    The pack descriptions follow, because "10 x 10" alone does not say what
    the ten are in.
    """
    packs = _container_rows(product)
    described = "; ".join(
        f"{row['description']}" + (f" ({row['material']})" if row["material"] else "")
        for row in packs
    )
    if product.pack_size and described:
        return f"{product.pack_size} — {described}"
    if product.pack_size:
        return product.pack_size
    return described or MISSING


def shelf_life_statement(product) -> tuple[str, str]:
    """The shelf life as the three documents print it, and its provenance.

    **The claim is what is printed; the data is what justifies it.** The
    claim lives on `Product.shelf_life_months` and the evidence lives in
    the timepoint results, and rule R05 refuses to let them disagree --
    exactly the shape P21 gave 3.2.P.8.1 and P22 gave the comparator.

    WHY the documents print the claim rather than the supported figure,
    when 3.2.P.8.1 prints the supported figure: 3.2.P.8.1 is an argument
    ABOUT the data and belongs beside it, while a label is a statement of
    what was authorised. A label silently printing a shorter period than
    the application asked for would file a shelf life nobody applied for.
    So the claim is printed, R05 blocks the export when the data does not
    reach it, and the provenance string names the supported figure so a
    filer reading the comparison screen sees both numbers at once.
    """
    long_term = [
        study for study in product.stability if study.study_type is StabilityStudyType.LONG_TERM
    ]
    supported, basis = supported_months(long_term)
    if product.shelf_life_months is None:
        return MISSING, (
            f"Not yet claimed. Your long-term stability data supports "
            f"{supported} months ({basis})."
        )
    return (
        f"{product.shelf_life_months} months",
        f"Claimed on the product (step 1 of the wizard); your long-term stability "
        f"data supports {supported} months ({basis}). Rule R05 blocks the export "
        f"if the claim exceeds it.",
    )


def shared_values(product) -> list[SharedValue]:
    """Every fact that appears in more than one of 1.3.1 / 1.3.2 / 1.3.3.

    This is the single source the three documents render from. Adding a
    shared fact means adding it HERE, once -- which is what stops the next
    shared fact from being typed three times.
    """
    shelf_life, shelf_life_source = shelf_life_statement(product)
    excipients = [excipient.name for excipient in product.excipients]
    return [
        SharedValue(
            field="product_name",
            label="Name of the medicinal product",
            value=" ".join(
                part
                for part in (
                    product.brand_name,
                    product.strength_display,
                    product.dosage_form.value if product.dosage_form else "",
                )
                if part
            ),
            source="Brand name, the strengths on your active ingredients, and the dosage form.",
            smpc_section="1",
        ),
        SharedValue(
            field="strength",
            label="Strength",
            value=product.strength_display or MISSING,
            # Named precisely, because this is the field a filer is most
            # surprised to find read-only: strength is not a product
            # column at all, it is one per active ingredient, which is
            # what makes a combination product representable.
            source="The strength on each active ingredient (step 2 of the wizard).",
            smpc_section="2",
        ),
        SharedValue(
            field="dosage_form",
            label="Pharmaceutical form",
            value=product.dosage_form.value if product.dosage_form else MISSING,
            source="Dosage form on the product (step 1 of the wizard).",
            smpc_section="3",
        ),
        SharedValue(
            field="route_of_administration",
            label="Route of administration",
            value=product.route_of_administration or MISSING,
            source="Route of administration on the product (step 1 of the wizard).",
            smpc_section="4.2",
        ),
        SharedValue(
            field="excipients",
            label="List of excipients",
            value="; ".join(excipients) or MISSING,
            source=(
                "Your excipient rows (step 3 of the wizard), which are also what "
                "3.2.P.4.1 is built from. Rule R28 checks them against the batch "
                "formula in both directions."
            ),
            smpc_section="6.1",
        ),
        SharedValue(
            field="shelf_life",
            label="Shelf life",
            value=shelf_life,
            source=shelf_life_source,
            smpc_section="6.3",
        ),
        SharedValue(
            field="storage_condition",
            label="Special precautions for storage",
            value=product.storage_condition or MISSING,
            source=(
                "Storage condition on the product (step 1 of the wizard). Rule R29 "
                "checks it against the temperature your long-term study actually ran at."
            ),
            smpc_section="6.4",
        ),
        SharedValue(
            field="container",
            label="Nature and contents of container",
            value=container_statement(product),
            source=(
                "Your declared pack size and the packaging rows that 3.2.P.7 is "
                "built from (steps 1 and 4 of the wizard)."
            ),
            smpc_section="6.5",
        ),
        SharedValue(
            field="legal_status",
            label="Legal status of supply",
            value=product.legal_status.value if product.legal_status else MISSING,
            source="Legal status on the product (step 1 of the wizard).",
            smpc_section="Annex",
        ),
    ]


def shared_block(product) -> dict[str, str]:
    """`shared_values` as a flat `{field: value}` dict for a template.

    The templates bind `shared.shelf_life` rather than looping, because a
    document's layout is not a table of key/value pairs -- an SmPC has
    numbered headings in a fixed order. The dict is what lets all three
    bind the same names.
    """
    return {value.field: value.value for value in shared_values(product)}


def _effect_rows(information) -> list[dict[str, str]]:
    """Undesirable effects, grouped the way both documents must print them:
    in frequency-band order, most common first.

    Sorted by the band's position in `AdverseEventFrequency`, so the SmPC
    and the leaflet cannot order them differently -- and an unrecognised
    band sorts last rather than raising, because a rendered document that
    shows the odd entry at the end is more useful than a build that fails.
    """
    rows = [
        {
            "effect": str(entry.get("effect", "")),
            "frequency": str(entry.get("frequency", "")),
        }
        for entry in information.adverse_effects
    ]
    return sorted(
        rows,
        key=lambda row: (
            _FREQUENCY_ORDER.get(row["frequency"], len(_FREQUENCY_ORDER)),
            row["effect"],
        ),
    )


def _authored(information, attribute: str) -> str:
    """An authored SmPC section, or the missing marker.

    Present as a helper rather than inline so that "no product information
    row at all" and "a row with that section empty" render identically:
    both are a section the filer still owes, and rule R30 is what says so.
    """
    if information is None:
        return MISSING
    return getattr(information, attribute) or MISSING


def _authored_list(information, attribute: str) -> list[str]:
    if information is None:
        return []
    return list(getattr(information, attribute))


def _common(project) -> dict:
    """What all three documents carry that is not a `SharedValue`.

    The marketing authorisation holder is here rather than in
    `shared_values` because it is a fact about the FILING, not about the
    medicine -- the same product filed by a different applicant in a
    different country has a different holder, which is why it comes off
    `project.applicant` like every other document's applicant block does.
    """
    product = project.product
    return {
        "product": product,
        "shared": shared_block(product),
        "generic_name": product.generic_name,
        "marketing_authorisation_holder": (
            project.applicant.company_name if project.applicant else MISSING
        ),
        "marketing_authorisation_holder_address": (
            project.applicant.address
            if project.applicant and project.applicant.address
            else MISSING
        ),
        "manufacturer_name": (product.manufacturers[0].name if product.manufacturers else MISSING),
    }


def smpc_context(section, project, narrative) -> dict:
    """1.3.1 -- the Summary of Product Characteristics.

    HYBRID, and the split is the point: sections 1 to 3 and 6.1 to 6.5 are
    derived, sections 4.1 to 4.9 are authored data, and only 5.1 to 5.3 are
    narrative. A slot in 4.1 could invent an indication; a slot in 6.3
    could state a shelf life the stability data disproves. Neither is
    reachable from this context.
    """
    product = project.product
    information = product.product_information
    return {
        **_common(project),
        "section_number": section.number,
        "section_title": section.title,
        "therapeutic_indications": _authored(information, "therapeutic_indications"),
        "posology_and_administration": _authored(information, "posology_and_administration"),
        "contraindications": _authored_list(information, "contraindication_terms"),
        "special_warnings": _authored_list(information, "warning_terms"),
        "interactions": _authored(information, "interactions"),
        "pregnancy_and_lactation": _authored(information, "pregnancy_and_lactation"),
        "effects_on_driving": _authored(information, "effects_on_driving"),
        "undesirable_effects": (_effect_rows(information) if information is not None else []),
        "overdose": _authored(information, "overdose"),
        "incompatibilities": _authored(information, "incompatibilities"),
        "disposal": _authored(information, "special_precautions_for_disposal"),
        "narrative": narrative,
    }


def label_context(section, project) -> dict:
    """1.3.2 -- the outer and inner labels, in one document.

    GENERATED, with no narrative slot anywhere, and this is the strongest
    case for that in the whole platform: everything a label may legally
    carry is a fact already on file, and a label is read as the definitive
    statement of what is in the pack. There is nothing here for a model to
    draft that would not be a regulatory claim.

    ONE document for both labels, because that is what the target TOC's own
    leaf says ("Labelling (outer and inner labels)") and what NAFDAC asks
    for. The two differ in WHAT THEY FIT, not in what they say: the inner
    label of a blister strip has room for the name, strength, batch and
    expiry and nothing else, so it renders as a subset of the same values
    rather than from a second dataset.
    """
    common = _common(project)
    shared = common["shared"]
    return {
        **common,
        "section_number": section.number,
        "section_title": section.title,
        # The outer carton carries everything; the inner (immediate)
        # label carries the minimum set. Both are built from `shared`, so
        # a value can only ever be on both or on neither.
        "outer_label_rows": [
            {"label": "Name of the medicinal product", "value": shared["product_name"]},
            {"label": "Active ingredient(s) and strength", "value": shared["strength"]},
            {"label": "Pharmaceutical form", "value": shared["dosage_form"]},
            {"label": "Route of administration", "value": shared["route_of_administration"]},
            {"label": "List of excipients", "value": shared["excipients"]},
            {"label": "Contents", "value": shared["container"]},
            {"label": "Shelf life", "value": shared["shelf_life"]},
            {"label": "Storage", "value": shared["storage_condition"]},
            {"label": "Legal status", "value": shared["legal_status"]},
            {
                "label": "Marketing authorisation holder",
                "value": common["marketing_authorisation_holder"],
            },
            {"label": "Manufactured by", "value": common["manufacturer_name"]},
        ],
        "inner_label_rows": [
            {"label": "Name of the medicinal product", "value": shared["product_name"]},
            {"label": "Strength", "value": shared["strength"]},
            {"label": "Route of administration", "value": shared["route_of_administration"]},
            {"label": "Storage", "value": shared["storage_condition"]},
        ],
        # Batch number and expiry date are printed by the packing line at
        # the moment of packing, not by this platform: they are per-batch
        # facts, and a dossier that filled them in would be filing one
        # batch's label as the artwork for all of them. The label renders
        # the FIELD, marked as overprinted, which is what an assessor
        # reviewing artwork expects to see.
        "overprinted_fields": ["Batch number", "Manufacturing date", "Expiry date"],
    }


def leaflet_context(section, project, narrative) -> dict:
    """1.3.3 -- the patient information leaflet.

    HYBRID in a different way from the SmPC. The leaflet says the SAME
    facts, so every fact here comes from `shared` or from the authored
    clinical particulars; what the narrative slots supply is the plain
    LANGUAGE around them, in the PATIENT register.

    WHY the structured lists are printed as well as the narrative that
    paraphrases them: a leaflet is legally required to carry the
    contraindications, and a paraphrase can silently drop one. The list is
    the guarantee, the prose is the readability, and rule R32 checks that
    the prose did not lose an entry the list holds.
    """
    product = project.product
    information = product.product_information
    return {
        **_common(project),
        "section_number": section.number,
        "section_title": section.title,
        "contraindications": _authored_list(information, "contraindication_terms"),
        "special_warnings": _authored_list(information, "warning_terms"),
        "undesirable_effects": (_effect_rows(information) if information is not None else []),
        "disposal": _authored(information, "special_precautions_for_disposal"),
        "narrative": narrative,
    }
