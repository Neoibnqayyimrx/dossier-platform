"""Section registry for the real docxtpl template engine (P04).

This is the successor to the Markdown prototype in `section_map.py` (kept
as-is — `render_p1` there still backs `test_rendered_section_cannot_contain_
bugs` and `run_demo.py`, which predate this module and test a different
concern: that the rule engine catches real LAMOX copy-paste bugs, not the
template engine itself).

WHY a typed dataclass registry instead of a plain dict of strings: P07/P08
will iterate over every registered section to assemble a full dossier, and
need to know, for each one, which template file to load and which narrative
slots P05 is allowed to fill. Encoding that as fields on `SectionSpec` means
"what sections exist and what they need" lives in one typed place, not
scattered across context.py's per-section branches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.target_toc import na_statement_leaves

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


@dataclass(frozen=True)
class SectionSpec:
    number: str
    title: str
    template_filename: str
    narrative_slots: list[str] = field(default_factory=list)
    # P05: what to search the P03 knowledge base for when grounding this
    # section's narrative. A deliberate, hand-written query per section —
    # not just reusing `title` verbatim — so retrieval targets what the
    # narrative actually needs to say, not just what the section is called.
    grounding_query: str | None = None
    # P04 chemical-structure capability: the context key the list of
    # per-drug-substance 2D structure images is bound to, if this section's
    # template has one. None (the default) means "no image slot" -- any
    # section can opt in by naming a key here and looping over it in its
    # template; this is not QOS-specific.
    #
    # WHY a list and not a single image: 2.3.S (and 3.2.S) are repeated
    # PER DRUG SUBSTANCE -- a fixed-dose combination like AMPICLOX
    # (ampicillin + cloxacillin) owes the assessor one structural formula
    # per active, not one for "the product". The template loops; the
    # single-API case is just a list of length one.
    structure_images_slot: str | None = None
    # P13: sections that are REPEATED per subject rather than appearing
    # once. "drug_substance" means one rendered document per active
    # ingredient -- 3.2.S is repeated per drug substance, and the ICH DTD
    # says so itself: `m3-2-s-drug-substance*` is starred, with `substance`
    # and `manufacturer` both #REQUIRED. None means the section appears
    # exactly once for the project, which is every section built before P13.
    repeat_per: str | None = None
    # P17: True when this section's entire content is a statement that the
    # section does not apply. Such a section is registered like any other --
    # so assembly, folder placement, the TOC and the eCTD backbone pick it
    # up with no special case -- but it is EMITTED only for projects whose
    # applicability says so (see app/templating/instances.py). Every other
    # section is emitted for every project, which is exactly the assumption
    # P17 removed.
    is_statement: bool = False

    @property
    def template_path(self) -> Path:
        return TEMPLATES_DIR / self.template_filename


SECTIONS: dict[str, SectionSpec] = {
    "1.0": SectionSpec(
        number="1.0",
        title="Cover Letter",
        template_filename="cover_letter.docx",
        narrative_slots=["purpose"],
        grounding_query="administrative submission requirements cover letter",
    ),
    "1.2": SectionSpec(
        number="1.2",
        title="Application / Registration Form",
        template_filename="registration_form.docx",
        # No narrative slots: unlike the cover letter, every fact on a
        # registration form is already structured data (applicant, product,
        # region) -- there is nothing here for P05's LLM to draft. A good
        # example that not every Module 1 document needs narrative prose.
        narrative_slots=[],
        grounding_query=None,
    ),
    "3.2.P.1": SectionSpec(
        number="3.2.P.1",
        title="Description and Composition of Drug Product",
        template_filename="section_3_2_p_1.docx",
        narrative_slots=["description"],
        grounding_query="description and composition of the drug product dosage form",
    ),
    "3.2.P.8.1": SectionSpec(
        number="3.2.P.8.1",
        title="Stability Summary and Conclusion",
        template_filename="stability_summary.docx",
        narrative_slots=["conclusion"],
        grounding_query="stability testing storage conditions retest period shelf life",
    ),
    "3.2.S.1": SectionSpec(
        number="3.2.S.1",
        title="General Information (Drug Substance)",
        template_filename="section_3_2_s_1.docx",
        narrative_slots=["general_properties"],
        grounding_query="drug substance nomenclature structure general properties",
        structure_images_slot="structures",
        repeat_per="drug_substance",
    ),
    "3.2.S.4.1": SectionSpec(
        number="3.2.S.4.1",
        title="Specification (Drug Substance)",
        template_filename="section_3_2_s_4_1.docx",
        # No narrative slots: a specification is a table of commitments,
        # every cell of which is structured data. There is nothing here for
        # the LLM to draft -- same reasoning as the registration form (1.2).
        narrative_slots=[],
        grounding_query=None,
        repeat_per="drug_substance",
    ),
    "2.3": SectionSpec(
        number="2.3",
        title="Quality Overall Summary",
        template_filename="section_2_3_qos.docx",
        narrative_slots=["overview"],
        grounding_query="quality overall summary drug substance drug product",
        structure_images_slot="structures",
    ),
}

# The not-applicable statements, registered from the target TOC rather than
# typed out fourteen times (P17).
#
# WHY generated into the same dict instead of kept in a parallel one: every
# consumer of SECTIONS -- assembly, the /sections endpoint, the eCTD
# backbone -- would otherwise need to learn about a second registry, and the
# first one to forget would silently drop the statements from its output.
# One registry, one iteration, and a statement leaf is just a section whose
# template happens to be short.
#
# They are appended AFTER the hand-written entries, which is fine because
# nothing depends on this dict's order: CTD folder placement comes from
# app.ctd.structure and eCTD sibling order from index_xml's _CHILD_ORDER,
# both of which encode the real declared order rather than trusting this
# one (see index_xml's module docstring on exactly that trap).
NA_STATEMENT_TEMPLATE = "na_statement.docx"

for _leaf in na_statement_leaves():
    SECTIONS[_leaf.number] = SectionSpec(
        number=_leaf.number,
        title=_leaf.title,
        template_filename=NA_STATEMENT_TEMPLATE,
        # No narrative slots, deliberately. A statement of inapplicability is
        # a regulatory claim whose wording comes from the guideline, not from
        # a model -- this is the clearest case in the whole platform of the
        # determinism boundary (AGENTS.md §5).
        narrative_slots=[],
        grounding_query=None,
        is_statement=True,
    )


def get_section(number: str) -> SectionSpec:
    try:
        return SECTIONS[number]
    except KeyError:
        raise KeyError(
            f"No registered section {number!r}; registered sections: {', '.join(SECTIONS)}"
        )
