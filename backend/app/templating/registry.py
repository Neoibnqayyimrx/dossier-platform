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

from app.models.enums import NarrativeRegister
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
    # P22: emit this section ONLY for a project whose applicability says it
    # applies. The default is False, which is the pre-P22 behaviour --
    # every registered section is emitted for every project.
    #
    # WHY this is not the same flag as `is_statement`: a statement leaf is
    # emitted when the section does NOT apply, and this is its mirror --
    # emitted when it DOES. Both read the same resolution
    # (app.ctd.region_profiles.resolve_applicability), which is what makes
    # the biowaiver decision in the wizard actually change the package:
    # answering "yes" to 1.2.17 is not a preference recorded somewhere, it
    # is a document appearing in Module 1.
    #
    # It is also what keeps a NAFDAC-only Module 1 leaf out of an EU
    # package. The EU applicability table is empty, meaning "not modelled",
    # so nothing is claimed and nothing is emitted -- rather than the eCTD
    # builder raising on a leaf it has no folder for.
    only_when_applicable: bool = False
    # P22: this rendered document ACCOMPANIES an uploaded one at the same
    # section, rather than being the section's only leaf.
    #
    # WHY it is needed at all: assembly keys leaves by instance key, and an
    # uploaded file WINS over a rendered one at the same key (see
    # app/assembly/assemble.py) -- which is right, because a generated
    # stand-in for a signed certificate is not an improvement on the
    # certificate. 5.3.1.2 is the case where it is wrong: the CRO's study
    # report and a structured summary of the study data are two DIFFERENT
    # documents that both belong under that heading, and the eCTD DTD
    # agrees -- `m5-3-1-2-...` has a `leaf*` content model, not one leaf.
    # Without a distinct key the summary would be silently dropped the
    # moment the report was attached, which is precisely the "looks
    # complete, is not" failure this platform exists to prevent.
    leaf_suffix: str | None = None
    # P23: WHO this section's narrative is written for, which decides how
    # its output is judged (app/narrative/guardrails.py) and which system
    # prompt it is generated under.
    #
    # WHY a declared property of the section rather than just a different
    # prompt for the leaflet: a prompt is an instruction a model may
    # quietly ignore, and nothing downstream would know it had. A patient
    # information leaflet has a statutory plain-language obligation that an
    # SmPC does not -- "contraindicated in hepatic impairment" is correct
    # in one document and a failure in the other -- so the obligation has
    # to be checkable on the OUTPUT and gatable at export (rule R33). One
    # register per section, not per slot: every slot of 1.3.3 addresses a
    # patient and every slot of 1.3.1 addresses a prescriber, and a
    # section that needed both voices would be two documents.
    narrative_register: NarrativeRegister = NarrativeRegister.REGULATORY

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
        grounding_query=("post approval stability protocol commitment production batches annual"),
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
    # ---- P23: product information -- one dataset, three audiences ------
    #
    # The SmPC, the labels and the leaflet. They say the same facts to a
    # prescriber, to whoever is holding the pack, and to the patient, and in
    # real filings they contradict each other constantly -- a shelf-life
    # extension updates two of the three. All three render from
    # app/templating/product_information.py's `shared_values`, so there is
    # one expression of each shared fact and nothing to disagree with.
    #
    # Note the three different production types in one group, and that they
    # are not a style choice: the label is GENERATED because everything on
    # it is a fact already on file, the SmPC is HYBRID with its 5.x
    # descriptive sections drafted, and the leaflet is HYBRID in the
    # PATIENT register because its job is to re-say known facts in plain
    # language.
    "1.3.1": SectionSpec(
        number="1.3.1",
        title="Summary of Product Characteristics (SmPC)",
        template_filename="smpc.docx",
        # The 5.x sections ONLY. Sections 4.1-4.9 are authored data on
        # ProductInformation, not slots: an indication, a dose and a
        # contraindication are regulatory CLAIMS, and a model inventing one
        # is the single error the existing guardrails cannot catch -- there
        # is no number to leak and no citation to fabricate. See
        # app/models/product_information.py.
        narrative_slots=[
            "pharmacodynamic_properties",
            "pharmacokinetic_properties",
            "preclinical_safety",
        ],
        grounding_query=(
            "summary of product characteristics pharmacodynamic pharmacokinetic "
            "properties preclinical safety data"
        ),
    ),
    "1.3.2": SectionSpec(
        number="1.3.2",
        title="Labelling (outer and inner labels)",
        template_filename="labelling.docx",
        # NO NARRATIVE SLOTS, and this is the strongest case for that in the
        # platform after 1.4.1. A label is read as the definitive statement
        # of what is in the pack; everything it may legally carry is already
        # on file, so a slot here could only add a regulatory claim nobody
        # made.
        narrative_slots=[],
        grounding_query=None,
    ),
    "1.3.3": SectionSpec(
        number="1.3.3",
        title="Package insert / Patient Information Leaflet",
        template_filename="patient_information_leaflet.docx",
        # Four slots, one per leaflet heading a patient recognises. Every
        # FACT in them is already printed from the shared values and the
        # authored particulars; what the slots supply is the language.
        narrative_slots=[
            "what_it_is_used_for",
            "before_you_take_it",
            "how_to_take_it",
            "possible_side_effects",
        ],
        grounding_query=(
            "patient information leaflet readability plain language package insert " "requirements"
        ),
        narrative_register=NarrativeRegister.PATIENT,
    ),
    # ---- P22: bioequivalence -------------------------------------------
    #
    # Four documents built from one set of study data, and the spread
    # across modules is the point. 1.4.1 is a MODULE 1 form; 5.2 is a
    # MODULE 5 table; the summary sits with the study report in 5.3.1.2.
    # A filer entering the confidence intervals once is the only way those
    # three can be guaranteed to agree, and they are exactly the three an
    # assessor cross-reads.
    "1.4.1": SectionSpec(
        number="1.4.1",
        title="Bioequivalence Trial Information (BTI) form",
        template_filename="bti_form.docx",
        # NO NARRATIVE SLOTS, and this one is emphatic. The target TOC's
        # own note on this leaf reads "Derived entirely from the BE study
        # data. No prose." A form an agency reads field-by-field has no
        # place for a drafted paragraph, and a slot here would be a slot
        # that could state a confidence interval the results table
        # disproves.
        narrative_slots=[],
        grounding_query=None,
        only_when_applicable=True,
    ),
    "5.2": SectionSpec(
        number="5.2",
        title="Tabular Listing of All Clinical Studies",
        template_filename="clinical_study_listing.docx",
        narrative_slots=[],
        grounding_query=None,
    ),
    "5.3.1.2": SectionSpec(
        number="5.3.1.2",
        title="Bioequivalence Study Summary",
        template_filename="be_study_summary.docx",
        narrative_slots=[],
        grounding_query=None,
        # Ships BESIDE the CRO's uploaded report rather than instead of it.
        leaf_suffix="summary",
    ),
    "1.2.17": SectionSpec(
        number="1.2.17",
        title="Biowaiver Request — BCS-based Bioavailability Study",
        template_filename="biowaiver_request.docx",
        # HYBRID: the BCS class, the solubility and permeability claim and
        # the f2 similarity factor are data; the argument that ties them
        # together is the applicant's own and is genuinely theirs to write.
        narrative_slots=["justification"],
        grounding_query=(
            "biowaiver BCS biopharmaceutics classification solubility permeability "
            "dissolution similarity f2"
        ),
        only_when_applicable=True,
    ),
    "1.2.18": SectionSpec(
        number="1.2.18",
        title="Biowaiver Request — Additional Strength",
        template_filename="biowaiver_request.docx",
        narrative_slots=["justification"],
        grounding_query=(
            "biowaiver additional strength proportional composition dissolution profile "
            "comparison"
        ),
        only_when_applicable=True,
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
