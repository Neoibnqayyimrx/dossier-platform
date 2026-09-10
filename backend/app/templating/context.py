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
from app.models.enums import (
    CertificateType,
    PackagingComponent,
    PackagingRole,
    TSE_RELEVANT_ORIGINS,
)
from app.models.project import Project
from app.templating import (
    bioequivalence,
    development,
    literature,
    product_information,
    qis,
    qos,
    quality_control,
    stability,
)
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

    # ---- P24d: the two Module 1 forms, and the two open questions -------
    #
    # 1.2.1 and 1.2.2 share this branch because they render from the same
    # records -- which is the whole reason filing both is safe (see the
    # target TOC's note on 1.2.1). `application_details` is added for
    # 1.2.1's own table; 1.2.2's template does not read it and is
    # unchanged.
    if section_number in ("1.2.1", "1.2.2"):
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
            "application_details": [
                {"label": "Product", "value": product.brand_name},
                {"label": "Strength", "value": product.strength_display},
                {
                    "label": "Dosage form",
                    "value": product.dosage_form.value if product.dosage_form else MISSING,
                },
                {
                    "label": "Applicant",
                    "value": applicant.company_name if applicant else MISSING,
                },
                {
                    "label": "Applicant address",
                    "value": applicant.address if applicant and applicant.address else MISSING,
                },
                {
                    "label": "Submission type",
                    "value": project.submission_type.value,
                },
                {"label": "Authority", "value": project.region.value},
            ],
        }

    if section_number == "1.2.14":
        return _gmp_inspection_context(project, narrative)

    if section_number == "1.6":
        return _samples_context(project)

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
    if section_number == "2.2":
        return _module_2_introduction_context(project, narrative)

    if section_number in ("3.3", "5.4"):
        return literature.literature_context(section, project)

    # ---- P24d: manufacture and pharmaceutical development ---------------
    #
    # Dispatched through a table for the same reason the quality-control
    # sections are: eleven sections built from three shapes. See
    # app/templating/development.py, and note that the 3.2.S.2 group takes
    # a SUBJECT (they repeat per drug substance) while the 3.2.P group
    # takes the project.
    if section_number in _DRUG_SUBSTANCE_MANUFACTURE:
        if subject is None:
            raise ValueError(
                f"Section {section_number} repeats per drug substance, so it needs a "
                f"subject; none was passed."
            )
        return development.drug_substance_manufacture_context(section, subject, narrative)

    if section_number in _DEVELOPMENT_SECTIONS:
        return _DEVELOPMENT_SECTIONS[section_number](section, project, narrative)

    # ---- P24: the derived documents -------------------------------------
    #
    # Dispatched before everything else in Module 1 because they are not
    # Module 1 documents in any meaningful sense -- 1.4.2 is Module 3 in a
    # form layout, and its context comes from the Module 3 section contexts
    # rather than from any model this function reads. See
    # app/templating/derived.py.
    if section_number == "1.4.2":
        return qis.qis_context(section, project)

    if section_number == "1.4.1":
        return bioequivalence.bti_context(section, project)

    if section_number == "5.2":
        return bioequivalence.clinical_listing_context(section, project)

    if section_number == "5.3.1.2":
        return bioequivalence.be_study_summary_context(section, project)

    if section_number in ("1.2.17", "1.2.18"):
        return bioequivalence.biowaiver_context(section, project, narrative)

    # ---- P23: the three product-information documents -------------------
    #
    # Three leaves, one dataset. They are dispatched separately rather than
    # through the quality-control table above because that table is keyed on
    # an OWNER (a substance, an excipient, the product), and these three
    # have the same owner as each other -- what differs is the AUDIENCE. See
    # app/templating/product_information.py, whose `shared_values` all three
    # read, which is what makes them unable to disagree.
    if section_number == "1.3.1":
        return product_information.smpc_context(section, project, narrative)

    if section_number == "1.3.2":
        return product_information.label_context(section, project)

    if section_number == "1.3.3":
        return product_information.leaflet_context(section, project, narrative)

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
        #
        # P24c: what WAS a two-key dict is now the fourteen-subsection QOS,
        # assembled from Module 3's own contexts (app/templating/qos.py).
        # `product` and `narrative` are still returned, unchanged, because
        # the template's heading, structure loop and overview slot are
        # unchanged -- the summary grew, it did not move.
        return qos.qos_context(section, project, narrative)

    raise ValueError(f"No context builder for section {section_number!r}")


def _module_2_introduction_context(project, narrative) -> dict:
    """2.2 -- the one page that orients an assessor before Module 2's
    summaries.

    Every particular here is printed from the same records 1.3.1, the label
    and 3.2.P.1 print, so the introduction cannot open Module 2 with a
    strength or a route that the rest of the dossier contradicts. That is
    not a hypothetical: the introduction is written first, early in a
    project, and is the page least likely to be revisited when a strength
    or a pack changes.
    """
    product = project.product
    applicant = project.applicant
    particulars = [
        ("Product", product.brand_name),
        ("Generic name", product.generic_name or MISSING),
        ("Strength", product.strength_display),
        ("Dosage form", product.dosage_form.value if product.dosage_form else MISSING),
        ("Route of administration", product.route_of_administration or MISSING),
        ("Pack size", product.pack_size or MISSING),
        ("Applicant", applicant.company_name if applicant else MISSING),
        ("Submission type", project.submission_type.value),
    ]
    return {
        "introduction_statement": (
            f"This application is made by "
            f"{applicant.company_name if applicant else MISSING} for the registration of "
            f"{product.brand_name} with {project.region.value}, as a "
            f"{project.submission_type.value.replace('-', ' ')} application. The "
            f"particulars are those filed throughout this dossier."
        ),
        "particulars": [{"label": label, "value": value} for label, value in particulars],
        "narrative": narrative,
    }


def _gmp_inspection_context(project, narrative) -> dict:
    """1.2.14 -- the invitation letter for GMP inspection.

    NAFDAC inspects the sites that make the medicine, and the invitation
    has to name them with the addresses an inspector will travel to. Those
    come from the manufacturer records that 3.2.P.3.1 also renders, so an
    address corrected in the wizard is corrected in the invitation.

    The API manufacturer is INCLUDED here, unlike in 3.2.P.3.1 (which is
    about the finished product only). An agency inspecting a generic's
    supply chain may inspect the API site too, and omitting it from an
    invitation would be the applicant deciding what the agency may look at.
    """
    product = project.product
    applicant = project.applicant
    sites = [m for m in product.manufacturers if m.role is not None]
    return {
        "authority": project.region.value,
        "applicant_name": applicant.company_name if applicant else MISSING,
        "product_name": product.brand_name,
        "registration_type": (
            product.registration_type.value if product.registration_type else MISSING
        ),
        "invitation_statement": (
            f"{applicant.company_name if applicant else MISSING} invites "
            f"{project.region.value} to inspect the manufacturing sites listed below in "
            f"connection with this application for {product.brand_name}."
        ),
        "sites": [
            {
                "name": site.name,
                "address": site.site_address or MISSING,
                "role": site.role.value,
                "gmp": (
                    f"{site.gmp_status.value if site.gmp_status else MISSING}"
                    f" / {site.manufacturing_licence or 'no licence on file'}"
                ),
            }
            for site in sites
        ],
        "authorized_representative": (
            applicant.authorized_representative_name
            if applicant and applicant.authorized_representative_name
            else MISSING
        ),
        "narrative": narrative,
    }


def _samples_context(project) -> dict:
    """1.6 -- Samples, the target's second open question.

    Physical samples are not a document, so what this leaf owes is a record
    of what was sent: which batches, made when, in which pack. The batches
    are the SAME rows 3.2.P.5.4 files, so a sample cannot be presented
    under a batch number the dossier has no analysis for -- which is
    precisely the disconnect that makes a laboratory result impossible to
    reconcile with a submission.
    """
    product = project.product
    batches = sorted(product.batch_analyses, key=lambda b: b.batch_number)
    packs = [
        pack.description
        for pack in product.packaging
        if pack.role is not PackagingRole.DRUG_SUBSTANCE
        and pack.component is PackagingComponent.SECONDARY
    ]
    pack = packs[0] if packs else (product.pack_size or MISSING)
    return {
        "samples_statement": (
            f"Samples of {product.brand_name} from the batches below are submitted to "
            f"{project.region.value} for laboratory analysis."
            if batches
            else (
                f"[[NO BATCHES ON FILE -- 1.6 cannot state which samples of "
                f"{product.brand_name} were submitted]]"
            )
        ),
        "samples": [
            {
                "batch_number": batch.batch_number,
                "manufacture_date": (
                    batch.manufacture_date.isoformat() if batch.manufacture_date else MISSING
                ),
                "pack": pack,
                "filed_at": "3.2.P.5.4",
            }
            for batch in batches
        ],
    }


# ---- P24d dispatch ---------------------------------------------------------
#
# The four 3.2.S.2 sections that repeat per drug substance and share one
# builder: what differs between them is the section number, the title and
# which paragraph the narrative slot holds -- all of which the SectionSpec
# already carries.
_DRUG_SUBSTANCE_MANUFACTURE = frozenset({"3.2.S.2.2", "3.2.S.2.3", "3.2.S.2.4", "3.2.S.2.6"})

# The drug-product development sections, each with its own builder because
# each derives a genuinely different table. Section number -> builder,
# rather than a shape name and a second lookup: there is one builder per
# section here, so the indirection would buy nothing.
_DEVELOPMENT_SECTIONS = {
    "3.2.P.2.1": development.components_context,
    "3.2.P.2.2": development.formulation_context,
    "3.2.P.2.3": development.process_development_context,
    "3.2.P.2.4": development.container_development_context,
    "3.2.P.2.5": development.microbiological_context,
    # Both 3.2.P.3 sections take the same builder. They are two questions
    # about one process -- how it runs, and where it is controlled -- and
    # the frame an assessor reads either against (sites, batch size,
    # composition) is identical. The narrative slot is what differs, and
    # the registry already says so.
    "3.2.P.3.3": development.drug_product_manufacture_context,
    "3.2.P.3.4": development.drug_product_manufacture_context,
}


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
