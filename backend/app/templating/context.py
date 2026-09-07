"""Context builder for the template engine (P04).

Given a `Project` (which carries the `Product` plus the target `Region` —
the "authority" a cover letter addresses is a *filing* decision, not a fact
about the product, which is why this takes a Project rather than a bare
Product) and a section number, assemble the exact dict docxtpl needs to
render that section's template.

Narrative slots are always present in the returned context, defaulting to
`None` so the template's `narrative.x or '[[AI DRAFT PENDING ...]]'`
fallback renders a clearly-marked placeholder — never call the LLM here
(P05's job), and never leave a slot silently missing from the context,
which would raise a Jinja Undefined error instead of rendering a placeholder.
"""

from __future__ import annotations

from app.ctd.region_profiles import REGION_PROFILES, resolve_applicability
from app.models.enums import CertificateType, PackagingRole, TSE_RELEVANT_ORIGINS
from app.models.project import Project
from app.templating import bioequivalence, quality_control, stability
from app.templating.registry import get_section

# What a context prints where a fact should be but is not. Shared rather
# than retyped per branch: it is the string a reader scans a rendered
# section for, so it must be one string.
MISSING = "[[NOT YET ON FILE]]"


def build_context(
    section_number: str,
    project: Project,
    narrative: dict[str, str] | None = None,
    subject=None,
) -> dict:
    """`subject` is the row this copy is about, for a section that repeats:
    a drug substance for 3.2.S, a manufacturing site for 3.2.P.3.1, a pack
    for 3.2.P.7. None for every once-per-project section -- see
    app/templating/instances.py."""
    section = get_section(section_number)
    narrative = {
        slot: narrative.get(slot) if narrative else None for slot in section.narrative_slots
    }
    product = project.product

    if section.is_statement:
        # P17. WHY this branch is FIRST and keyed on the spec rather than on
        # a list of section numbers: there are fourteen of these and there
        # will be more, and a `section_number in (...)` tuple here would be a
        # third place the set of statements is written down (after the target
        # TOC and the registry). Ask the spec what kind of section it is.
        resolved = resolve_applicability(project).get(section_number)
        return {
            "section_number": section_number,
            "section_title": section.title,
            # The citation is the load-bearing sentence. If the applicability
            # table has none, say so LOUDLY in the document rather than
            # printing a bare "not applicable" -- an uncited exclusion is the
            # thing an assessor queries, so it should be impossible to file
            # one by accident. Rendering the marker also means the leaf still
            # builds, so the gap shows up in the package under review rather
            # than as a crash at build time.
            "citation": (
                resolved.section.citation
                if resolved is not None and resolved.section.citation
                else "[[NO GUIDELINE CITED -- applicability table incomplete]]"
            ),
            "submission_type": project.submission_type.value,
            "applicant_name": (
                project.applicant.company_name if project.applicant else "[[NOT YET ON FILE]]"
            ),
            "product_name": product.brand_name,
        }

    if section_number == "1.0":
        return {
            "authority": project.region.value,
            "registration_type": (
                product.registration_type.value if product.registration_type else None
            ),
            "product": product,
            "manufacturer": product.manufacturers[0] if product.manufacturers else None,
            "narrative": narrative,
        }

    if section_number == "1.2":
        applicant = project.applicant
        authorized_representative = MISSING
        if applicant and applicant.authorized_representative_name:
            title = applicant.authorized_representative_title
            authorized_representative = (
                f"{applicant.authorized_representative_name}, {title}"
                if title
                else applicant.authorized_representative_name
            )
        return {
            "authority": project.region.value,
            "registration_type": (
                product.registration_type.value if product.registration_type else None
            ),
            "product": product,
            "applicant_name": applicant.company_name if applicant else MISSING,
            "applicant_address": applicant.address if applicant and applicant.address else MISSING,
            "applicant_country": applicant.country if applicant and applicant.country else MISSING,
            "contact_name": (
                applicant.contact_name if applicant and applicant.contact_name else MISSING
            ),
            "contact_email": (
                applicant.contact_email if applicant and applicant.contact_email else MISSING
            ),
            "authorized_representative": authorized_representative,
        }

    if section_number == "3.2.P.1":
        return {
            "product": product,
            "batch_formula": product.batch_formula,
            "narrative": narrative,
        }

    if section_number == "3.2.S.1":
        # Nomenclature as label/value rows rather than fixed template
        # placeholders: which identifiers a substance actually has varies
        # (many have no CAS on file, a salt form only exists for salts), and
        # a table of blank rows reads as missing data rather than as
        # "not applicable".
        rows = [("INN / common name", subject.inn_name)]
        if subject.salt_form:
            rows.append(("Salt / hydrate form as manufactured", subject.salt_form))
        if subject.compendial_std:
            rows.append(("Compendial standard", subject.compendial_std.value))
        if subject.manufacturer is not None:
            rows.append(("Manufacturer", subject.manufacturer.name))
        if subject.dmf_number:
            rows.append(("DMF number", subject.dmf_number))
        if subject.cep_number:
            rows.append(("CEP number", subject.cep_number))
        if subject.retest_period_months is not None:
            rows.append(("Retest period", f"{subject.retest_period_months} months"))
        return {
            "product": product,
            "substance": subject,
            "nomenclature": [{"label": label, "value": value} for label, value in rows],
            "narrative": narrative,
        }

    # ---- P20: the control sections ------------------------------------
    #
    # WHY these are dispatched through a table instead of eleven more `if`
    # branches: they are eleven sections built from four SHAPES -- a
    # specification table, a batch table, an impurity table, and a
    # narrative with one of those under it. The `if` chain below grew one
    # branch per section because each of those sections was genuinely
    # different; these are genuinely the same, and writing them as
    # branches would be writing the same builder eleven times. See
    # app/templating/quality_control.py.
    #
    # Note where `subject` comes from and where it does not. 3.2.S.4.1
    # repeats per drug substance and 3.2.P.4.1 per excipient, so the
    # subject IS the owner. 3.2.P.5.1 does not repeat, so its owner is the
    # product itself -- and 3.2.P.4.2 / 3.2.P.4.4 do not repeat either but
    # are ABOUT the excipients, so they take the whole list. Three
    # different answers to "what owns this section", resolved once here.
    if section_number in _QUALITY_CONTROL_SECTIONS:
        return _quality_control_context(section, project, subject, narrative)

    # ---- P22: the bioequivalence documents ------------------------------
    #
    # Four leaves across three modules, all built from the same study
    # rows -- see app/templating/bioequivalence.py. They take the PROJECT
    # rather than an owner, unlike the quality-control table above,
    # because two of them are Module 1 documents: a BTI form names the
    # applicant and a biowaiver request is a claim the filing makes, and
    # neither is a fact about a material.
    if section_number == "1.4.1":
        return bioequivalence.bti_context(section, project)

    if section_number == "5.2":
        return bioequivalence.clinical_listing_context(section, project)

    if section_number == "5.3.1.2":
        return bioequivalence.be_study_summary_context(section, project)

    if section_number in ("1.2.17", "1.2.18"):
        return bioequivalence.biowaiver_context(section, project, narrative)

    if section_number == "3.2.S.2.1":
        # WHY this renders a marker instead of raising when the manufacturer
        # is absent, where instances.drug_substance_info raises: this is a
        # human-readable page, and a page that says the maker is not on file
        # is reviewable evidence of a gap. The backbone is machine-read by
        # an agency's software and has nowhere to put that sentence, so it
        # must not be built at all. Rule R17 blocks the export either way.
        manufacturer = subject.manufacturer
        if manufacturer is None:
            rows = [("Manufacturer", MISSING)]
        else:
            rows = [
                ("Name", manufacturer.name),
                ("Site address", manufacturer.site_address or MISSING),
                ("Country", manufacturer.country or MISSING),
                ("Responsibility", "Manufacture of the drug substance"),
                (
                    "GMP status",
                    manufacturer.gmp_status.value if manufacturer.gmp_status else MISSING,
                ),
                ("Manufacturing licence", manufacturer.manufacturing_licence or MISSING),
            ]
            if subject.dmf_number:
                rows.append(("DMF number", subject.dmf_number))
            if subject.cep_number:
                rows.append(("CEP number", subject.cep_number))
        return {
            "product": product,
            "substance": subject,
            "manufacturer_details": [{"label": label, "value": value} for label, value in rows],
        }

    if section_number == "3.2.S.5":
        return {
            "product": product,
            "substance": subject,
            "standard_statement": _reference_standard_statement(
                subject.inn_name, subject.compendial_std
            ),
        }

    if section_number == "3.2.S.6":
        # The DRUG SUBSTANCE's packaging, never the finished product's --
        # `role` is what makes those two answerable from one model (P19).
        # A pack that names no substance applies to every substance: the
        # single-API case, and the combination whose actives ship alike.
        packs = [
            pack
            for pack in product.packaging
            if pack.role is PackagingRole.DRUG_SUBSTANCE
            and (pack.active_ingredient is None or pack.active_ingredient is subject)
        ]
        return {
            "product": product,
            "substance": subject,
            "packaging": packs,
            "storage_statement": (
                f"{subject.inn_name} is stored in the container closure system described "
                f"above under the conditions stated in 3.2.S.7.1."
                if packs
                else "[[NO DRUG SUBSTANCE PACKAGING ON FILE -- 3.2.S.6 cannot be completed]]"
            ),
        }

    if section_number == "3.2.P.3.1":
        rows = [
            ("Name", subject.name),
            ("Site address", subject.site_address or MISSING),
            ("Country", subject.country or MISSING),
            # The role IS the responsibility, which is what 3.2.P.3.1 asks
            # for: an assessor needs to know which site does what, not just
            # that four companies are involved.
            ("Responsibility", subject.role.value),
            ("GMP status", subject.gmp_status.value if subject.gmp_status else MISSING),
            ("Manufacturing licence", subject.manufacturing_licence or MISSING),
            ("WHO-GMP", "Yes" if subject.who_gmp else "No"),
            ("PIC/S", "Yes" if subject.pic_s else "No"),
        ]
        return {
            "product": product,
            "site": subject,
            "site_details": [{"label": label, "value": value} for label, value in rows],
        }

    if section_number == "3.2.P.3.2":
        # Reads product.batch_formula -- the SAME rows 3.2.P.1's composition
        # table reads. Two sections showing the same numbers cannot disagree
        # if neither has its own copy of them, which is what
        # test_batch_formula_cannot_disagree_with_the_composition_table pins.
        lines = list(product.batch_formula)
        return {
            "product": product,
            "batch_size": _batch_size(lines),
            "batch_formula": [
                {
                    "component": line.component,
                    "spec": line.spec,
                    "qty_per_unit_mg": line.qty_per_unit_mg,
                    # Computed, never read from declared_batch_qty_kg: that
                    # field is the filer's CLAIM, and rule R04 exists to
                    # check it against this arithmetic. Printing the claim
                    # here would file the unchecked number.
                    "batch_qty_kg": _batch_quantity_kg(line),
                    "role": "Active" if line.is_active else "Excipient",
                }
                for line in lines
            ],
        }

    if section_number == "3.2.P.4.5":
        return _excipient_origin_context(product)

    if section_number == "3.2.P.6":
        return {
            "product": product,
            "reference_standards": [
                {
                    "material": api.inn_name,
                    "claimed": api.compendial_std.value if api.compendial_std else MISSING,
                    "standard": _reference_standard_for(api.compendial_std),
                }
                for api in product.apis
            ],
        }

    if section_number == "3.2.P.7":
        rows = [
            ("Component", subject.component.value),
            ("Description", subject.description),
            ("Material", subject.material or MISSING),
            ("Artwork reference", subject.artwork_ref or MISSING),
            ("Pack size", product.pack_size or MISSING),
        ]
        return {
            "product": product,
            "pack": subject,
            "pack_details": [{"label": label, "value": value} for label, value in rows],
            "storage_statement": (
                f"The product is stored in this container closure system under the "
                f"conditions stated on the label: "
                f"{product.storage_condition or MISSING}"
            ),
        }

    if section_number == "3.2.R":
        profile = REGION_PROFILES.get(project.region)
        items = profile.regional_information if profile is not None else ()
        return {
            "region": project.region.value,
            "regional_information": items,
            "regional_statement": (
                f"The following regional information is filed for {project.region.value}."
                if items
                else (
                    f"No additional regional information is declared for "
                    f"{project.region.value} in this platform's region profile."
                )
            ),
        }

    if section_number == "2.3":
        # NOTE: `structure` (the chemical-structure image slot) is NOT set
        # here -- it's injected by render.py, which is the one place that
        # holds the live DocxTemplate instance an InlineImage must be bound
        # to. This function stays synchronous, DB-free, and Word-library-
        # free, same as every other branch.
        return {
            "product": product,
            "narrative": narrative,
        }

    raise ValueError(f"No context builder for section {section_number!r}")


def _batch_quantity_kg(line) -> float:
    """Quantity per unit (mg) x batch size (units), in kilograms.

    mg -> kg is a factor of 1e6. Rounded to four decimals because that is
    the precision the column is stored at (`Numeric(12, 4)`), and a
    rendered number longer than its stored one is a number that cannot be
    reproduced from the data.
    """
    return round(float(line.qty_per_unit_mg) * line.batch_size_units / 1e6, 4)


def _batch_size(lines) -> str:
    """The batch size the formula is stated for.

    Every line carries its own `batch_size_units`, which SHOULD all agree.
    Where they do not, this says so rather than picking the first: two
    batch sizes in one formula is a real, and serious, data error -- it
    means the columns do not add up to one batch -- and the leaf should
    show it rather than hide it behind whichever row happened to sort
    first.
    """
    sizes = {line.batch_size_units for line in lines}
    if not sizes:
        return MISSING
    if len(sizes) > 1:
        stated = ", ".join(f"{size:,}" for size in sorted(sizes))
        return f"[[INCONSISTENT BATCH SIZES ON FILE: {stated} units]]"
    return f"{sizes.pop():,} units"


def _reference_standard_for(compendial_std) -> str:
    """Which reference standard follows from the standard a material is
    claimed against.

    Deterministic and derived, not invented: claiming BP means using the BP
    reference substance for that monograph, and claiming in-house means a
    characterised working standard whose characterisation has to be filed.
    The one thing this must never do is name a catalogue number nobody
    entered.
    """
    if compendial_std is None:
        return MISSING
    if compendial_std.value == "in-house":
        return (
            "Characterised in-house working standard; characterisation filed in 3.2.S.3.1 "
            "and qualified against the specification in 3.2.S.4.1"
        )
    return f"{compendial_std.value} reference substance for the corresponding monograph"


def _reference_standard_statement(name: str, compendial_std) -> str:
    if compendial_std is None:
        return f"[[NO COMPENDIAL STANDARD ON FILE for {name} -- 3.2.S.5 cannot be completed]]"
    return (
        f"{name} is controlled against {compendial_std.value}. "
        f"Reference standard: {_reference_standard_for(compendial_std)}."
    )


def _excipient_origin_context(product) -> dict:
    """3.2.P.4.5: the TSE/BSE claim, generated from `Excipient.origin`.

    Three groups, and the third is the one that matters. Excipients of
    human or animal origin owe evidence; excipients declared otherwise are
    covered by the blanket statement; excipients NOBODY CLASSIFIED are
    named separately and explicitly, because a statement that no material
    is of animal origin, made over a list where three materials have no
    origin recorded, is a claim the filer never made. Rule R21 is the
    blocking half of the same fact.
    """
    of_concern = [e for e in product.excipients if e.origin in TSE_RELEVANT_ORIGINS]
    undeclared = [e for e in product.excipients if e.origin is None]

    # One TSE/BSE certificate on the product satisfies the whole list. WHY
    # not per excipient: `Certificate` has no excipient FK, so the platform
    # cannot yet tell which material a certificate covers -- recorded as a
    # known limitation in the P19 build-log entry rather than papered over
    # by pretending the link exists.
    has_certificate = any(
        certificate.certificate_type is CertificateType.TSE_BSE
        for certificate in product.certificates
    )
    evidence = (
        "TSE/BSE certificate on file (Module 1)"
        if has_certificate
        else "[[NO TSE/BSE CERTIFICATE ON FILE -- see rule R21]]"
    )

    if of_concern:
        origin_statement = (
            "The following excipients are of human or animal origin. Evidence of "
            "compliance with the current TSE/BSE guidance is filed for each."
        )
    else:
        origin_statement = (
            "No excipient used in the manufacture of this product is of human or animal origin."
        )

    return {
        "product": product,
        "origin_statement": origin_statement,
        "excipients_of_concern": [
            {
                "name": excipient.name,
                "function": excipient.function.value if excipient.function else MISSING,
                "origin": excipient.origin.value,
                "evidence": evidence,
            }
            for excipient in of_concern
        ],
        "undeclared_statement": (
            "Origin not yet declared for: "
            + ", ".join(sorted(excipient.name for excipient in undeclared))
            + ". The statement above does not cover these materials."
            if undeclared
            else ""
        ),
    }


# ---- P20/P21 dispatch ------------------------------------------------------
#
# Section number -> (shape, how to find the owner). Kept as one table so
# that "which owner does this section render from" is answerable by reading
# one screen, rather than by tracing eleven branches -- and so that adding
# 3.2.P.2 or a second impurity leaf later is a row, not a branch.
#
# The owner resolvers:
#   "subject"    -- the section repeats, so the instance's subject is the
#                   owner (a drug substance, or an excipient).
#   "product"    -- the section appears once and is about the medicine.
#   "excipients" -- the section appears once but is about every excipient.
_SUBJECT, _PRODUCT, _EXCIPIENTS = "subject", "product", "excipients"

_QUALITY_CONTROL_SECTIONS: dict[str, tuple[str, str]] = {
    "3.2.S.4.1": ("specification", _SUBJECT),
    "3.2.P.4.1": ("specification", _SUBJECT),
    "3.2.P.5.1": ("specification", _PRODUCT),
    "3.2.S.3.2": ("impurities", _SUBJECT),
    "3.2.P.5.5": ("impurities", _PRODUCT),
    "3.2.S.4.4": ("batches", _SUBJECT),
    "3.2.P.5.4": ("batches", _PRODUCT),
    "3.2.S.4.2": ("procedures", _SUBJECT),
    "3.2.P.4.2": ("procedures", _EXCIPIENTS),
    "3.2.P.5.2": ("procedures", _PRODUCT),
    "3.2.P.4.4": ("justification", _EXCIPIENTS),
    "3.2.P.5.6": ("justification", _PRODUCT),
    # P21: the stability sections, on exactly the same table. 3.2.S.7
    # repeats per drug substance and 3.2.P.8 is about the medicine, which
    # the two owner resolvers already answer -- adding six sections here
    # was six rows and no branches, which is what P20's table was for.
    #
    # Note 3.2.P.8.1 lost its own `if` branch when it joined this table. It
    # used to render `product.stability` and a free-text result summary;
    # it now renders what the timepoint data supports, from the same
    # function rule R05 checks against.
    "3.2.S.7.1": ("stability_summary", _SUBJECT),
    "3.2.P.8.1": ("stability_summary", _PRODUCT),
    "3.2.S.7.2": ("stability_commitment", _SUBJECT),
    "3.2.P.8.2": ("stability_commitment", _PRODUCT),
    "3.2.S.7.3": ("stability_data", _SUBJECT),
    "3.2.P.8.3": ("stability_data", _PRODUCT),
}


def _quality_control_context(section, project, subject, narrative) -> dict:
    shape, owner_source = _QUALITY_CONTROL_SECTIONS[section.number]
    product = project.product

    if owner_source == _SUBJECT:
        # A repeating section with no subject is a caller bug, not a data
        # gap -- expand_sections never produces one. Raising names the
        # section rather than letting an AttributeError name a field.
        if subject is None:
            raise ValueError(
                f"Section {section.number} repeats along {section.repeat!r}, so it needs "
                f"a subject; none was passed."
            )
        owner = subject
    elif owner_source == _PRODUCT:
        owner = product
    else:
        owner = None

    if shape == "specification":
        return quality_control.specification_context(section, owner)
    if shape == "impurities":
        return quality_control.impurities_context(section, owner)
    if shape == "batches":
        return quality_control.batch_analysis_context(section, owner)
    if shape == "stability_summary":
        return stability.stability_summary_context(section, owner, narrative)
    if shape == "stability_data":
        return stability.stability_data_context(section, owner)
    if shape == "stability_commitment":
        return stability.stability_commitment_context(section, owner, narrative)

    # The two narrative shapes take a LIST of owners: 3.2.P.4.2 and
    # 3.2.P.4.4 cover every excipient in one document, while their drug
    # substance and drug product counterparts cover exactly one thing. One
    # builder either way -- a list of length one is not a special case.
    owners = list(product.excipients) if owner_source == _EXCIPIENTS else [owner]
    if shape == "procedures":
        return quality_control.analytical_procedures_context(section, owners, narrative)
    return quality_control.justification_context(section, owners, narrative)
