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

from app.models.project import Project
from app.templating.registry import get_section


def build_context(
    section_number: str, project: Project, narrative: dict[str, str] | None = None
) -> dict:
    section = get_section(section_number)
    narrative = {
        slot: narrative.get(slot) if narrative else None for slot in section.narrative_slots
    }
    product = project.product

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
