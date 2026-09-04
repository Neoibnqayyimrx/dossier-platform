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

from app.ctd.region_profiles import resolve_applicability
from app.models.project import Project
from app.templating.registry import get_section


def build_context(
    section_number: str,
    project: Project,
    narrative: dict[str, str] | None = None,
    subject=None,
) -> dict:
    """`subject` is the drug substance this copy is about, for sections that
    repeat per drug substance (3.2.S). None for every once-per-project
    section -- see app/templating/instances.py."""
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
        _MISSING = "[[NOT YET ON FILE]]"
        authorized_representative = _MISSING
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
            "applicant_name": applicant.company_name if applicant else _MISSING,
            "applicant_address": applicant.address if applicant and applicant.address else _MISSING,
            "applicant_country": applicant.country if applicant and applicant.country else _MISSING,
            "contact_name": (
                applicant.contact_name if applicant and applicant.contact_name else _MISSING
            ),
            "contact_email": (
                applicant.contact_email if applicant and applicant.contact_email else _MISSING
            ),
            "authorized_representative": authorized_representative,
        }

    if section_number == "3.2.P.1":
        return {
            "product": product,
            "batch_formula": product.batch_formula,
            "narrative": narrative,
        }

    if section_number == "3.2.P.8.1":
        return {
            "product": product,
            "stability": product.stability,
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

    if section_number == "3.2.S.4.1":
        return {
            "product": product,
            "substance": subject,
            # Sorted here, not just relied on from the relationship's
            # order_by: that ordering only applies when the rows are loaded
            # from the database, so an object built in memory (a seed, a
            # test, an API create) would render in insertion order. The
            # rendered table has to be deterministic either way -- the
            # builders must be byte-identical across runs.
            "specification": sorted(subject.specification, key=lambda r: r.sort_order),
            "narrative": narrative,
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
