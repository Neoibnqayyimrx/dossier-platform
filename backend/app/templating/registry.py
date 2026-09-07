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
    # P13/P19: the AXIS this section repeats along -- the name of a
    # collection on the project, resolved by `app.templating.instances`'
    # REPEAT_AXES table. "drug_substance" means one rendered document per
    # active ingredient, and the ICH DTD says so itself:
    # `m3-2-s-drug-substance*` is starred, with `substance` and
    # `manufacturer` both #REQUIRED. None means the section appears exactly
    # once for the project.
    #
    # WHY a field naming an axis rather than P13's module-level
    # REPEAT_PER_DRUG_SUBSTANCE constant and its `if`: 3.2.S was simply the
    # first repeating section, not a special one. 3.2.P.3.1 repeats per
    # manufacturing site, 3.2.P.7 per pack, 3.2.P.4.1 per excipient. The
    # spelling matches the `repeat:` key the target TOC already uses for
    # each of those leaves, and a test asserts the two agree.
    repeat: str | None = None
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
    # ---- P21: one set of stability sections, two owners -----------------
    #
    # 3.2.S.7.1-.3 and 3.2.P.8.1-.3 share three templates for the same
    # reason 3.2.S.4.1 and 3.2.P.5.1 share `specification.docx`: they are
    # the same section asked of two different materials, and six templates
    # would be six places for one table to be laid out differently.
    #
    # 3.2.P.8.1 keeps its number, its title and its template FILENAME, and
    # is a different document underneath: it used to print a claimed shelf
    # life beside a free-text result summary, and now prints what the
    # timepoint data supports. Keeping the filename is deliberate -- the
    # leaf path, the folder and the eCTD element are all unchanged, so a
    # rebuild of an existing sequence produces the same tree.
    "3.2.P.8.1": SectionSpec(
        number="3.2.P.8.1",
        title="Stability Summary and Conclusion",
        template_filename="stability_summary.docx",
        # The conclusion ONLY. The period, the storage statement and the
        # study table are all computed -- a narrative slot that could state
        # a shelf life is a slot that can contradict 3.2.P.8.3.
        narrative_slots=["conclusion"],
        grounding_query="stability testing storage conditions retest period shelf life",
    ),
    "3.2.P.8.2": SectionSpec(
        number="3.2.P.8.2",
        title="Post-approval Stability Protocol and Stability Commitment",
        template_filename="stability_commitment.docx",
        # The commitment's wording is a legal undertaking the applicant
        # makes; the schedule it follows is read from the studies.
        narrative_slots=["commitment"],
        grounding_query=(
            "post approval stability protocol commitment production batches annual"
        ),
    ),
    "3.2.P.8.3": SectionSpec(
        number="3.2.P.8.3",
        title="Stability Data (Drug Product)",
        template_filename="stability_data.docx",
        # No narrative slots: a stability table is timepoints, results and
        # the limits they are judged against. There is nothing here for the
        # LLM to draft -- the same call 3.2.S.4.1 and 3.2.P.5.4 make.
        narrative_slots=[],
        grounding_query=None,
    ),
    "3.2.S.7.1": SectionSpec(
        number="3.2.S.7.1",
        title="Stability Summary and Conclusion (Drug Substance)",
        template_filename="stability_summary.docx",
        narrative_slots=["conclusion"],
        grounding_query="drug substance stability retest period storage conditions",
        repeat="drug_substance",
    ),
    "3.2.S.7.2": SectionSpec(
        number="3.2.S.7.2",
        title="Post-approval Stability Protocol and Stability Commitment (Drug Substance)",
        template_filename="stability_commitment.docx",
        narrative_slots=["commitment"],
        grounding_query=(
            "post approval stability protocol commitment drug substance retest period"
        ),
        repeat="drug_substance",
    ),
    "3.2.S.7.3": SectionSpec(
        number="3.2.S.7.3",
        title="Stability Data (Drug Substance)",
        template_filename="stability_data.docx",
        narrative_slots=[],
        grounding_query=None,
        repeat="drug_substance",
    ),
    "3.2.S.1": SectionSpec(
        number="3.2.S.1",
        title="General Information (Drug Substance)",
        template_filename="section_3_2_s_1.docx",
        narrative_slots=["general_properties"],
        grounding_query="drug substance nomenclature structure general properties",
        structure_images_slot="structures",
        repeat="drug_substance",
    ),
    # ---- P20: one specification template, three owners -----------------
    #
    # 3.2.S.4.1, 3.2.P.4.1 and 3.2.P.5.1 all name `specification.docx`. That
    # is the same call the model layer made one level up (app/models/
    # spec_owner.py): a specification is ONE artifact asked for of three
    # different things, and three near-identical templates would be three
    # places for the same table to be laid out differently. P13's
    # `section_3_2_s_4_1.docx` was deleted rather than left beside its
    # replacement -- an unreferenced binary template is exactly the kind of
    # thing that rots unnoticed.
    "3.2.S.4.1": SectionSpec(
        number="3.2.S.4.1",
        title="Specification (Drug Substance)",
        template_filename="specification.docx",
        # No narrative slots: a specification is a table of commitments,
        # every cell of which is structured data. There is nothing here for
        # the LLM to draft -- same reasoning as the registration form (1.2).
        narrative_slots=[],
        grounding_query=None,
        repeat="drug_substance",
    ),
    "3.2.P.4.1": SectionSpec(
        number="3.2.P.4.1",
        title="Specification (Excipients)",
        template_filename="specification.docx",
        narrative_slots=[],
        grounding_query=None,
        # Per EXCIPIENT -- the axis P19 declared and deliberately left
        # unused, because `SpecificationTest` could not yet belong to an
        # excipient. Registering this section is now a registry entry
        # rather than a new branch, which was the whole point of P19.
        repeat="excipient",
    ),
    "3.2.P.5.1": SectionSpec(
        number="3.2.P.5.1",
        title="Specification (Drug Product)",
        template_filename="specification.docx",
        narrative_slots=[],
        grounding_query=None,
        # No repeat: there is exactly one finished product. The asymmetry
        # is real, not an oversight -- 3.2.S and 3.2.P.4 are about
        # MATERIALS, of which there can be several, and 3.2.P.5 is about
        # the medicine, of which there is one.
    ),
    # ---- P20: batches, impurities, and the prose that sits beside them --
    "3.2.S.3.2": SectionSpec(
        number="3.2.S.3.2",
        title="Impurities (Drug Substance)",
        template_filename="impurities.docx",
        narrative_slots=[],
        grounding_query=None,
        repeat="drug_substance",
    ),
    "3.2.S.4.2": SectionSpec(
        number="3.2.S.4.2",
        title="Analytical Procedures (Drug Substance)",
        template_filename="analytical_procedures.docx",
        # HYBRID: the table of methods is generated from the specification
        # rows, and the narrative describes the in-house methods only.
        # Where the specification is pharmacopoeial an analytical procedure
        # reduces to a citation -- and reproducing the monograph would
        # breach AGENTS.md 5 -- so there is nothing for the LLM to write
        # about those rows at all.
        narrative_slots=["in_house_methods"],
        grounding_query="analytical procedure validation ICH Q2 specificity accuracy precision",
        repeat="drug_substance",
    ),
    "3.2.S.4.4": SectionSpec(
        number="3.2.S.4.4",
        title="Batch Analysis (Drug Substance)",
        template_filename="batch_analysis.docx",
        narrative_slots=[],
        grounding_query=None,
        repeat="drug_substance",
    ),
    "3.2.P.4.2": SectionSpec(
        number="3.2.P.4.2",
        title="Analytical Procedures (Excipients)",
        template_filename="analytical_procedures.docx",
        narrative_slots=["in_house_methods"],
        grounding_query="analytical procedure validation ICH Q2 specificity accuracy precision",
        # NOT repeated, unlike 3.2.P.4.1 beside it, and the target TOC says
        # so. One document listing every excipient's methods is what an
        # assessor wants; one document per excipient would be a folder of
        # one-line files.
    ),
    "3.2.P.4.4": SectionSpec(
        number="3.2.P.4.4",
        title="Justification of Specification (Excipients)",
        template_filename="justification_of_specification.docx",
        narrative_slots=["justification"],
        grounding_query="justification of specification acceptance criteria ICH Q6A",
    ),
    "3.2.P.5.2": SectionSpec(
        number="3.2.P.5.2",
        title="Analytical Procedures (Drug Product)",
        template_filename="analytical_procedures.docx",
        narrative_slots=["in_house_methods"],
        grounding_query="analytical procedure validation ICH Q2 specificity accuracy precision",
    ),
    "3.2.P.5.4": SectionSpec(
        number="3.2.P.5.4",
        title="Batch Analyses (Drug Product)",
        template_filename="batch_analysis.docx",
        narrative_slots=[],
        grounding_query=None,
    ),
    "3.2.P.5.5": SectionSpec(
        number="3.2.P.5.5",
        title="Characterisation of Impurities (Drug Product)",
        template_filename="impurities.docx",
        narrative_slots=[],
        grounding_query=None,
    ),
    "3.2.P.5.6": SectionSpec(
        number="3.2.P.5.6",
        title="Justification of Specification (Drug Product)",
        template_filename="justification_of_specification.docx",
        narrative_slots=["justification"],
        grounding_query="justification of specification acceptance criteria ICH Q6A",
    ),
    # ---- P19: the sections whose data the platform already held --------
    #
    # Every one of these is backed by a model that existed before this
    # phase and by rules that already read it: BatchFormulaLine backs the
    # 3.2.P.1 composition table and R04's salt-to-base arithmetic, Packaging
    # backs R12, Manufacturer backs R08/R09/R17. What was missing was not
    # data but a place to put it.
    "3.2.S.2.1": SectionSpec(
        number="3.2.S.2.1",
        title="Name and Address of Manufacturer (Drug Substance)",
        template_filename="section_3_2_s_2_1.docx",
        # No narrative slots: a name and an address are facts on file. See
        # 1.2's WHY -- not every section has prose for the LLM to draft.
        narrative_slots=[],
        grounding_query=None,
        repeat="drug_substance",
    ),
    "3.2.S.5": SectionSpec(
        number="3.2.S.5",
        title="Reference Standards or Materials (Drug Substance)",
        template_filename="section_3_2_s_5.docx",
        narrative_slots=[],
        grounding_query=None,
        repeat="drug_substance",
    ),
    "3.2.S.6": SectionSpec(
        number="3.2.S.6",
        title="Container Closure System (Drug Substance)",
        template_filename="section_3_2_s_6.docx",
        narrative_slots=[],
        grounding_query=None,
        repeat="drug_substance",
    ),
    "3.2.P.3.1": SectionSpec(
        number="3.2.P.3.1",
        title="Manufacturer (Drug Product)",
        template_filename="section_3_2_p_3_1.docx",
        narrative_slots=[],
        grounding_query=None,
        repeat="manufacturing_site",
    ),
    "3.2.P.3.2": SectionSpec(
        number="3.2.P.3.2",
        title="Batch Formula",
        template_filename="section_3_2_p_3_2.docx",
        narrative_slots=[],
        grounding_query=None,
    ),
    "3.2.P.4.5": SectionSpec(
        number="3.2.P.4.5",
        title="Excipients of Human or Animal Origin",
        # NOT a P17 statement leaf, though it reads like one: `is_statement`
        # means "this section does not apply to this filing", and 3.2.P.4.5
        # always applies. What it says -- that no excipient is of human or
        # animal origin, or that these are and here is their TSE/BSE
        # evidence -- is generated FROM DATA either way.
        template_filename="section_3_2_p_4_5.docx",
        narrative_slots=[],
        grounding_query=None,
    ),
    "3.2.P.6": SectionSpec(
        number="3.2.P.6",
        title="Reference Standards or Materials (Drug Product)",
        template_filename="section_3_2_p_6.docx",
        narrative_slots=[],
        grounding_query=None,
    ),
    "3.2.P.7": SectionSpec(
        number="3.2.P.7",
        title="Container Closure System (Drug Product)",
        template_filename="section_3_2_p_7.docx",
        narrative_slots=[],
        grounding_query=None,
        repeat="pack",
    ),
    "3.2.R": SectionSpec(
        number="3.2.R",
        title="Regional Information",
        template_filename="section_3_2_r.docx",
        narrative_slots=[],
        grounding_query=None,
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
