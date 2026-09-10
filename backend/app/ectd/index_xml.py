"""ICH backbone (`index.xml`) builder (P09).

WHY a small per-parent "declared child order" table (`_CHILD_ORDER`)
instead of just appending headings in whatever order sections happen to
be registered: the DTD's content models are ORDERED sequences (e.g.
`m3-2-p-1-...?, m3-2-p-2-...?, ..., m3-2-p-8-stability?`), not unordered
sets -- libxml2 rejects a document where present elements appear out of
that declared order. `app.templating.registry.SECTIONS`' own dict order
happens to match DTD order for the 3 CTD headings this project currently
populates, but relying on that coincidence would silently break the
moment a new section is registered out of CTD-numeric order. This table
makes the real DTD sequence the single source of truth for sibling
order -- the same "small whitelist that fails loudly rather than guesses"
instinct as `app.ctd.structure.folder_for_section`.

Module 1 is DELIBERATELY not represented here at all. The ICH DTD itself
declares `m1-administrative-information-and-prescribing-information` as a
flat `(leaf*)` bag with no real substructure -- the actual Module 1
hierarchy lives in the *regional* backbone (`app.ectd.regional`), which is
how real eCTD submissions do it too: index.xml covers m2-m5, the regional
XML covers m1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from app.ectd.leaf import Leaf, build_leaf_element

ECTD_NS = "http://www.ich.org/ectd"
DTD_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "reference"
    / "ectd_dtd"
    / "ich-ectd-3-2.dtd"
)

# section_number (an app.templating.registry.SECTIONS key) -> the chain of
# ICH heading element names from just under the ectd:ectd root down to the
# element the leaf itself is filed under.
ICH_HEADING_PATH: dict[str, tuple[str, ...]] = {
    "2.2": ("m2-common-technical-document-summaries", "m2-2-introduction"),
    "2.3": ("m2-common-technical-document-summaries", "m2-3-quality-overall-summary"),
    "3.2.P.1": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-1-description-and-composition-of-the-drug-product",
    ),
    "3.2.P.8.1": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-8-stability",
        "m3-2-p-8-1-stability-summary-and-conclusion",
    ),
    # P17: the not-applicable statements. Each is filed under the heading
    # the section itself would occupy -- the eCTD equivalent of putting the
    # statement in the empty folder. Element names are taken verbatim from
    # ich-ectd-3-2.dtd; a typo here fails DTD validation loudly, which is
    # the behaviour we want.
    "2.4": ("m2-common-technical-document-summaries", "m2-4-nonclinical-overview"),
    "2.5": ("m2-common-technical-document-summaries", "m2-5-clinical-overview"),
    "2.6": (
        "m2-common-technical-document-summaries",
        "m2-6-nonclinical-written-and-tabulated-summaries",
    ),
    "2.7": ("m2-common-technical-document-summaries", "m2-7-clinical-summary"),
    "3.2.P.4.6": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-4-control-of-excipients",
        "m3-2-p-4-6-novel-excipients",
    ),
    "3.2.A": ("m3-quality", "m3-2-body-of-data", "m3-2-a-appendices"),
    # The module-level statement hangs directly off m4, since it speaks for
    # the whole module rather than for 4.2 or 4.3 (see the "4.0" note in
    # app.ctd.structure).
    "4.0": ("m4-nonclinical-study-reports",),
    "5.3.1.3": (
        "m5-clinical-study-reports",
        "m5-3-clinical-study-reports",
        "m5-3-1-reports-of-biopharmaceutic-studies",
        "m5-3-1-3-in-vitro-in-vivo-correlation-study-reports",
    ),
    "5.3.2": (
        "m5-clinical-study-reports",
        "m5-3-clinical-study-reports",
        "m5-3-2-reports-of-studies-pertinent-to-pharmacokinetics-using-human-biomaterials",
    ),
    "5.3.3": (
        "m5-clinical-study-reports",
        "m5-3-clinical-study-reports",
        "m5-3-3-reports-of-human-pharmacokinetics-pk-studies",
    ),
    "5.3.4": (
        "m5-clinical-study-reports",
        "m5-3-clinical-study-reports",
        "m5-3-4-reports-of-human-pharmacodynamics-pd-studies",
    ),
    # 5.3.5 is the exception, and it is an instructive one. The DTD declares
    # `m5-3-5-reports-of-efficacy-and-safety-studies*` -- starred, repeating
    # PER INDICATION, with `indication` #REQUIRED -- exactly the shape
    # `m3-2-s-drug-substance` has for substances. A not-applicable statement
    # has no indication to name, and inventing one ("not applicable") would
    # put a fabricated regulatory fact into the backbone, which is precisely
    # the class of thing this platform refuses to do.
    #
    # So the statement is filed one level up, as a leaf directly under
    # m5-3, whose content model begins with `leaf*` and permits exactly
    # this. It reads correctly too: the statement speaks for the whole of
    # 5.3.5, not for one indication within it -- the same reasoning that
    # gives Module 4 a single "4.0" statement. Its CTD folder is unchanged;
    # only the backbone placement differs, because only the backbone has
    # this constraint.
    "5.3.5": ("m5-clinical-study-reports", "m5-3-clinical-study-reports"),
    "5.3.6": (
        "m5-clinical-study-reports",
        "m5-3-clinical-study-reports",
        "m5-3-6-reports-of-postmarketing-experience",
    ),
    "5.3.7": (
        "m5-clinical-study-reports",
        "m5-3-clinical-study-reports",
        "m5-3-7-case-report-forms-and-individual-patient-listings",
    ),
    # P18: the uploaded third-party leaves. WHY they need entries here even
    # though nothing renders them: `build_index_xml` SILENTLY SKIPS a leaf
    # whose section key has no heading path (that is deliberate -- it is how
    # Module 1 documents stay out of index.xml and go in the regional
    # backbone instead). Without these, an uploaded BE study report would be
    # written into the package, checksummed, listed in the CTD table of
    # contents, and then quietly omitted from the eCTD backbone -- present on
    # disk and invisible to the agency's software.
    "3.2.P.3.5": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-3-manufacture",
        "m3-2-p-3-5-process-validation-and-or-evaluation",
    ),
    "3.2.P.4.3": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-4-control-of-excipients",
        "m3-2-p-4-3-validation-of-analytical-procedures",
    ),
    "3.2.P.5.3": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-5-control-of-drug-product",
        "m3-2-p-5-3-validation-of-analytical-procedures",
    ),
    # P24d: pharmaceutical development. All five 3.2.P.2 leaves share ONE
    # heading element, and that is the DTD's own shape rather than a
    # simplification: `m3-2-p-2-pharmaceutical-development` is declared
    # `((leaf | node-extension)*)` with no sub-elements, unlike
    # m3-2-p-3-manufacture beside it, which declares five. So the CTD
    # folder tree has five named folders (a human navigates that) and the
    # backbone has five leaves under one element (an agency's software
    # renders that). Placement and backbone structure are separate maps for
    # exactly this reason.
    "3.2.P.2.1": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-2-pharmaceutical-development",
    ),
    "3.2.P.2.2": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-2-pharmaceutical-development",
    ),
    "3.2.P.2.3": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-2-pharmaceutical-development",
    ),
    "3.2.P.2.4": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-2-pharmaceutical-development",
    ),
    "3.2.P.2.5": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-2-pharmaceutical-development",
    ),
    "3.2.P.3.3": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-3-manufacture",
        "m3-2-p-3-3-description-of-manufacturing-process-and-process-controls",
    ),
    "3.2.P.3.4": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-3-manufacture",
        "m3-2-p-3-4-controls-of-critical-steps-and-intermediates",
    ),
    "3.3": ("m3-quality", "m3-3-literature-references"),
    # P19: the data-ready generated leaves. 3.2.P.3.1 and 3.2.P.7 REPEAT
    # (per manufacturing site, per pack) and yet appear here rather than in
    # a per-subject table like the drug substance's: the DTD declares
    # `m3-2-p-3-1-manufacturers` and `m3-2-p-7-container-closure-system`
    # ONCE each, with `leaf*` content -- so three packs are three leaves
    # under one heading, not three headings. Only 3.2.S has a repeating
    # heading ELEMENT, because only there does the spec demand the subject
    # be named in an attribute.
    "3.2.P.3.1": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-3-manufacture",
        "m3-2-p-3-1-manufacturers",
    ),
    "3.2.P.3.2": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-3-manufacture",
        "m3-2-p-3-2-batch-formula",
    ),
    "3.2.P.4.5": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-4-control-of-excipients",
        "m3-2-p-4-5-excipients-of-human-or-animal-origin",
    ),
    "3.2.P.6": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-6-reference-standards-or-materials",
    ),
    "3.2.P.7": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-7-container-closure-system",
    ),
    # P20: the control sections that appear once. Note 3.2.P.4.2 and
    # 3.2.P.4.4 sit under `m3-2-p-4-control-of-excipients` with NO
    # `excipient` attribute, while 3.2.P.4.1 gets one element per excipient
    # -- see REPEATING_ELEMENTS below. Both are legal, because the DTD
    # declares that element starred with `excipient` #IMPLIED.
    "3.2.P.4.2": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-4-control-of-excipients",
        "m3-2-p-4-2-analytical-procedures",
    ),
    "3.2.P.4.4": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-4-control-of-excipients",
        "m3-2-p-4-4-justification-of-specifications",
    ),
    "3.2.P.5.1": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-5-control-of-drug-product",
        "m3-2-p-5-1-specifications",
    ),
    "3.2.P.5.2": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-5-control-of-drug-product",
        "m3-2-p-5-2-analytical-procedures",
    ),
    "3.2.P.5.4": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-5-control-of-drug-product",
        "m3-2-p-5-4-batch-analyses",
    ),
    "3.2.P.5.5": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-5-control-of-drug-product",
        "m3-2-p-5-5-characterisation-of-impurities",
    ),
    "3.2.P.5.6": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-5-control-of-drug-product",
        "m3-2-p-5-6-justification-of-specifications",
    ),
    # P21: the drug-product stability leaves. Element names verbatim from
    # ich-ectd-3-2.dtd -- a typo here fails DTD validation loudly, which is
    # the behaviour we want. Note 3.2.P.8.1's element is SINGULAR
    # ("...-conclusion") while 3.2.S.7.1's is plural ("...-conclusions");
    # that asymmetry is the DTD's, not a mistake, and copying one to the
    # other would produce a backbone no agency's software can read.
    "3.2.P.8.2": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-8-stability",
        "m3-2-p-8-2-post-approval-stability-protocol-and-stability-commitment",
    ),
    "3.2.P.8.3": (
        "m3-quality",
        "m3-2-body-of-data",
        "m3-2-p-drug-product",
        "m3-2-p-8-stability",
        "m3-2-p-8-3-stability-data",
    ),
    "3.2.R": ("m3-quality", "m3-2-body-of-data", "m3-2-r-regional-information"),
    # P22. Element name verbatim from ich-ectd-3-2.dtd; it is a direct
    # child of m5, not of m5-3, and `_CHILD_ORDER` below already declares
    # it first among m5's children.
    "5.2": ("m5-clinical-study-reports", "m5-2-tabular-listing-of-all-clinical-studies"),
    "5.3.1.1": (
        "m5-clinical-study-reports",
        "m5-3-clinical-study-reports",
        "m5-3-1-reports-of-biopharmaceutic-studies",
        "m5-3-1-1-bioavailability-study-reports",
    ),
    "5.3.1.2": (
        "m5-clinical-study-reports",
        "m5-3-clinical-study-reports",
        "m5-3-1-reports-of-biopharmaceutic-studies",
        "m5-3-1-2-comparative-ba-and-bioequivalence-study-reports",
    ),
    "5.3.1.4": (
        "m5-clinical-study-reports",
        "m5-3-clinical-study-reports",
        "m5-3-1-reports-of-biopharmaceutic-studies",
        "m5-3-1-4-reports-of-bioanalytical-and-analytical-methods-for-human-studies",
    ),
    "5.4": ("m5-clinical-study-reports", "m5-4-literature-references"),
}

# Sections repeated per drug substance: the heading chain BELOW the
# per-substance `m3-2-s-drug-substance` element. That element is inserted
# for us, with its required attributes, by build_index_xml.
DRUG_SUBSTANCE_HEADING_PATH: dict[str, tuple[str, ...]] = {
    "3.2.S.1": ("m3-2-s-1-general-information",),
    "3.2.S.4.1": ("m3-2-s-4-control-of-drug-substance", "m3-2-s-4-1-specification"),
    # P18: uploaded per-substance artifacts.
    "3.2.S.2.5": (
        "m3-2-s-2-manufacture",
        "m3-2-s-2-5-process-validation-and-or-evaluation",
    ),
    "3.2.S.3.1": (
        "m3-2-s-3-characterisation",
        "m3-2-s-3-1-elucidation-of-structure-and-other-characteristics",
    ),
    "3.2.S.4.3": (
        "m3-2-s-4-control-of-drug-substance",
        "m3-2-s-4-3-validation-of-analytical-procedures",
    ),
    # P19.
    "3.2.S.2.1": ("m3-2-s-2-manufacture", "m3-2-s-2-1-manufacturer"),
    # P24d: the four narrative manufacture sections, filed under the
    # per-substance element beside 3.2.S.2.1 and 3.2.S.2.5.
    "3.2.S.2.2": (
        "m3-2-s-2-manufacture",
        "m3-2-s-2-2-description-of-manufacturing-process-and-process-controls",
    ),
    "3.2.S.2.3": ("m3-2-s-2-manufacture", "m3-2-s-2-3-control-of-materials"),
    "3.2.S.2.4": (
        "m3-2-s-2-manufacture",
        "m3-2-s-2-4-controls-of-critical-steps-and-intermediates",
    ),
    "3.2.S.2.6": (
        "m3-2-s-2-manufacture",
        "m3-2-s-2-6-manufacturing-process-development",
    ),
    "3.2.S.5": ("m3-2-s-5-reference-standards-or-materials",),
    "3.2.S.6": ("m3-2-s-6-container-closure-system",),
    # P21: filed under the per-substance element, like every other 3.2.S
    # leaf -- which is what makes a combination product's two stability
    # datasets distinguishable in the backbone rather than only in the
    # folder tree.
    "3.2.S.7.1": ("m3-2-s-7-stability", "m3-2-s-7-1-stability-summary-and-conclusions"),
    "3.2.S.7.2": (
        "m3-2-s-7-stability",
        "m3-2-s-7-2-post-approval-stability-protocol-and-stability-commitment",
    ),
    "3.2.S.7.3": ("m3-2-s-7-stability", "m3-2-s-7-3-stability-data"),
    # P20.
    "3.2.S.3.2": ("m3-2-s-3-characterisation", "m3-2-s-3-2-impurities"),
    "3.2.S.4.2": (
        "m3-2-s-4-control-of-drug-substance",
        "m3-2-s-4-2-analytical-procedures",
    ),
    "3.2.S.4.4": (
        "m3-2-s-4-control-of-drug-substance",
        "m3-2-s-4-4-batch-analyses",
    ),
}

# Sections repeated per EXCIPIENT: the heading chain below the per-excipient
# `m3-2-p-4-control-of-excipients` element.
EXCIPIENT_HEADING_PATH: dict[str, tuple[str, ...]] = {
    "3.2.P.4.1": ("m3-2-p-4-1-specifications",),
}


@dataclass(frozen=True)
class RepeatingElement:
    """An axis whose sections repeat as a heading ELEMENT, not as leaves.

    P19 established that most repeating sections do NOT need this: the DTD
    declares `m3-2-p-3-1-manufacturers` and `m3-2-p-7-container-closure-
    system` once each with `leaf*` content, so three packs are three leaves
    under one heading. Only where the DTD stars the element itself does the
    HEADING repeat.

    P20 found the second such axis, and it was not obvious from the section
    numbers. `m3-2-p-4-control-of-excipients` is declared

        m3-2-p-4-control-of-excipients*   ... excipient CDATA #IMPLIED

    -- starred, with an attribute naming the subject: structurally the same
    shape as `m3-2-s-drug-substance`, arrived at from the other end of
    Module 3. So this is a table rather than the `if` P13 could get away
    with when the drug substance was the only case.

    One difference worth naming, because it is the spec making a judgement:
    `substance` and `manufacturer` on the drug-substance element are both
    #REQUIRED -- a drug substance cannot be filed anonymously -- while
    `excipient` here is #IMPLIED. The DTD is willing to accept an unnamed
    excipient section; this platform is not, and always sets the attribute,
    because an assessor reading two specification leaves under one heading
    needs to know which material each is about.
    """

    tag: str
    # Where the repeating element hangs, as a chain from the root.
    parent_path: tuple[str, ...]
    # Which attribute names the subject -- also the discriminator that keeps
    # two subjects' subtrees from being merged into one element (the P13
    # bug; see _Node).
    discriminator_attr: str
    # Section number -> the heading chain BELOW the repeating element.
    heading_paths: dict[str, tuple[str, ...]]


REPEATING_ELEMENTS: dict[str, RepeatingElement] = {
    "drug_substance": RepeatingElement(
        tag="m3-2-s-drug-substance",
        parent_path=("m3-quality", "m3-2-body-of-data"),
        discriminator_attr="substance",
        heading_paths=DRUG_SUBSTANCE_HEADING_PATH,
    ),
    "excipient": RepeatingElement(
        tag="m3-2-p-4-control-of-excipients",
        parent_path=("m3-quality", "m3-2-body-of-data", "m3-2-p-drug-product"),
        discriminator_attr="excipient",
        heading_paths=EXCIPIENT_HEADING_PATH,
    ),
}

# The DTD's real declared child order, keyed by parent element name
# ("ectd:ectd" for the document root itself). Only parents that can ever
# hold more than one *kind* of child need an entry here -- a heading we
# only ever attach leaves to (never a sub-heading) doesn't need one.
_CHILD_ORDER: dict[str, tuple[str, ...]] = {
    "ectd:ectd": (
        "m1-administrative-information-and-prescribing-information",
        "m2-common-technical-document-summaries",
        "m3-quality",
        "m4-nonclinical-study-reports",
        "m5-clinical-study-reports",
    ),
    "m2-common-technical-document-summaries": (
        "m2-2-introduction",
        "m2-3-quality-overall-summary",
        "m2-4-nonclinical-overview",
        "m2-5-clinical-overview",
        "m2-6-nonclinical-written-and-tabulated-summaries",
        "m2-7-clinical-summary",
    ),
    "m3-2-body-of-data": (
        "m3-2-s-drug-substance",
        "m3-2-p-drug-product",
        "m3-2-a-appendices",
        "m3-2-r-regional-information",
    ),
    "m3-2-p-drug-product": (
        "m3-2-p-1-description-and-composition-of-the-drug-product",
        "m3-2-p-2-pharmaceutical-development",
        "m3-2-p-3-manufacture",
        "m3-2-p-4-control-of-excipients",
        "m3-2-p-5-control-of-drug-product",
        "m3-2-p-6-reference-standards-or-materials",
        "m3-2-p-7-container-closure-system",
        "m3-2-p-8-stability",
    ),
    "m3-2-p-8-stability": (
        "m3-2-p-8-1-stability-summary-and-conclusion",
        "m3-2-p-8-2-post-approval-stability-protocol-and-stability-commitment",
        "m3-2-p-8-3-stability-data",
    ),
    # P17: Module 5 gains six not-applicable statements at once, which makes
    # m5-3 the first parent whose children arrive in an order that has
    # nothing to do with the DTD's -- exactly the trap this table exists for.
    "m5-clinical-study-reports": (
        "m5-2-tabular-listing-of-all-clinical-studies",
        "m5-3-clinical-study-reports",
        "m5-4-literature-references",
    ),
    "m5-3-clinical-study-reports": (
        "m5-3-1-reports-of-biopharmaceutic-studies",
        "m5-3-2-reports-of-studies-pertinent-to-pharmacokinetics-using-human-biomaterials",
        "m5-3-3-reports-of-human-pharmacokinetics-pk-studies",
        "m5-3-4-reports-of-human-pharmacodynamics-pd-studies",
        "m5-3-5-reports-of-efficacy-and-safety-studies",
        "m5-3-6-reports-of-postmarketing-experience",
        "m5-3-7-case-report-forms-and-individual-patient-listings",
    ),
    "m5-3-1-reports-of-biopharmaceutic-studies": (
        "m5-3-1-1-bioavailability-study-reports",
        "m5-3-1-2-comparative-ba-and-bioequivalence-study-reports",
        "m5-3-1-3-in-vitro-in-vivo-correlation-study-reports",
        "m5-3-1-4-reports-of-bioanalytical-and-analytical-methods-for-human-studies",
    ),
    "m3-quality": ("m3-2-body-of-data", "m3-3-literature-references"),
    "m3-2-s-drug-substance": (
        "m3-2-s-1-general-information",
        "m3-2-s-2-manufacture",
        "m3-2-s-3-characterisation",
        "m3-2-s-4-control-of-drug-substance",
        "m3-2-s-5-reference-standards-or-materials",
        "m3-2-s-6-container-closure-system",
        "m3-2-s-7-stability",
    ),
    "m3-2-s-2-manufacture": (
        "m3-2-s-2-1-manufacturer",
        "m3-2-s-2-2-description-of-manufacturing-process-and-process-controls",
        "m3-2-s-2-3-control-of-materials",
        "m3-2-s-2-4-controls-of-critical-steps-and-intermediates",
        "m3-2-s-2-5-process-validation-and-or-evaluation",
        "m3-2-s-2-6-manufacturing-process-development",
    ),
    "m3-2-s-7-stability": (
        "m3-2-s-7-1-stability-summary-and-conclusions",
        "m3-2-s-7-2-post-approval-stability-protocol-and-stability-commitment",
        "m3-2-s-7-3-stability-data",
    ),
    "m3-2-s-3-characterisation": (
        "m3-2-s-3-1-elucidation-of-structure-and-other-characteristics",
        "m3-2-s-3-2-impurities",
    ),
    "m3-2-s-4-control-of-drug-substance": (
        "m3-2-s-4-1-specification",
        "m3-2-s-4-2-analytical-procedures",
        "m3-2-s-4-3-validation-of-analytical-procedures",
        "m3-2-s-4-4-batch-analyses",
        "m3-2-s-4-5-justification-of-specification",
    ),
    "m3-2-p-3-manufacture": (
        "m3-2-p-3-1-manufacturers",
        "m3-2-p-3-2-batch-formula",
        "m3-2-p-3-3-description-of-manufacturing-process-and-process-controls",
        "m3-2-p-3-4-controls-of-critical-steps-and-intermediates",
        "m3-2-p-3-5-process-validation-and-or-evaluation",
    ),
    "m3-2-p-5-control-of-drug-product": (
        "m3-2-p-5-1-specifications",
        "m3-2-p-5-2-analytical-procedures",
        "m3-2-p-5-3-validation-of-analytical-procedures",
        "m3-2-p-5-4-batch-analyses",
        "m3-2-p-5-5-characterisation-of-impurities",
        "m3-2-p-5-6-justification-of-specifications",
    ),
    "m3-2-p-4-control-of-excipients": (
        "m3-2-p-4-1-specifications",
        "m3-2-p-4-2-analytical-procedures",
        "m3-2-p-4-3-validation-of-analytical-procedures",
        "m3-2-p-4-4-justification-of-specifications",
        "m3-2-p-4-5-excipients-of-human-or-animal-origin",
        "m3-2-p-4-6-novel-excipients",
    ),
}


class _Node:
    """One heading element in the backbone tree.

    Children are keyed by (tag, discriminator) rather than by tag alone,
    because `m3-2-s-drug-substance` is the first element that legitimately
    REPEATS as a sibling: the DTD declares it `m3-2-s-drug-substance*` with
    `substance` and `manufacturer` both #REQUIRED. Keying by tag alone
    would silently merge ampicillin's and cloxacillin's subtrees into one
    element -- and, being a merge rather than a crash, would have produced
    a DTD-VALID backbone that files two substances' documents under one
    substance's name.
    """

    __slots__ = ("tag", "attrs", "children", "leaves")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: dict[tuple[str, str], "_Node"] = {}
        self.leaves: list[Leaf] = []

    def child(self, tag: str, discriminator: str = "", attrs: dict[str, str] | None = None):
        key = (tag, discriminator)
        if key not in self.children:
            self.children[key] = _Node(tag, attrs)
        return self.children[key]


def _place_repeated_leaf(
    root_node: _Node, section_key: str, leaf: Leaf, axis: str, attrs: dict[str, str]
) -> None:
    """File one leaf under its own copy of a repeating heading element.

    P13 wrote this for the drug substance alone, when `m3-2-s-drug-
    substance` was the only starred heading anything was filed under. P20
    found the second (`m3-2-p-4-control-of-excipients`) and generalised
    rather than branching -- which is the lesson P19's build-log entry
    already recorded about `instances.py`: a single-case implementation
    does not look like it is making assumptions, because with one case
    every assumption is true.

    The discriminator is the attribute that names the subject. Without it
    `_Node` would key both excipients' subtrees by tag alone and MERGE
    them -- producing, exactly as it would have for two drug substances, a
    DTD-VALID backbone that files one material's specification under the
    other's name. A merge is far worse than a crash here, because nothing
    reports it.
    """
    element = REPEATING_ELEMENTS[axis]
    number = section_key.split("-", 1)[0]
    try:
        tail = element.heading_paths[number]
    except KeyError:
        raise ValueError(
            f"section {number!r} repeats per {axis} but has no heading path in "
            f"REPEATING_ELEMENTS[{axis!r}].heading_paths"
        )
    node = root_node
    for tag in element.parent_path:
        node = node.child(tag)
    node = node.child(
        element.tag,
        discriminator=attrs[element.discriminator_attr],
        attrs=attrs,
    )
    for tag in tail[:-1]:
        node = node.child(tag)
    node.child(tail[-1]).leaves.append(leaf)


def _attach(el: etree._Element, node: _Node) -> None:
    """Fill already-created element `el` with `node`'s leaves (first,
    per every heading's `leaf*` prefix in its content model) then its
    child headings, in real DTD-declared order."""
    for leaf in node.leaves:
        el.append(build_leaf_element(leaf))

    order = _CHILD_ORDER.get(node.tag)
    if order is None:
        keys = list(node.children)
    else:
        unknown = {tag for tag, _ in node.children} - set(order)
        if unknown:
            raise ValueError(
                f"{node.tag}: no declared DTD order for child(ren) {sorted(unknown)} -- "
                "add them to _CHILD_ORDER before registering a section that uses them"
            )
        # Sort by the DTD's declared order of the TAG, keeping repeated
        # siblings of one tag in insertion order relative to each other.
        keys = sorted(node.children, key=lambda k: order.index(k[0]))

    for key in keys:
        child = node.children[key]
        child_el = etree.SubElement(el, child.tag)
        for name, value in child.attrs.items():
            child_el.set(name, value)
        _attach(child_el, child)


def build_index_xml(
    leaves_by_section: dict[str, Leaf],
    repeat_info: dict[str, tuple[str, dict[str, str]]] | None = None,
) -> bytes:
    """Build and DTD-validate `index.xml` from this sequence's leaves,
    keyed by `section_key` (an `app.templating.registry.SECTIONS` number).
    Leaves whose `section_key` has no `ICH_HEADING_PATH` entry (Module 1
    documents) are silently skipped here -- they belong only in the
    regional backbone (`app.ectd.regional`).

    `repeat_info` maps an instance key to `(axis name, element attributes)`
    for the leaves that belong under a REPEATING heading element -- see
    `REPEATING_ELEMENTS` and `app.templating.instances.repeat_element_info`.
    P20 widened this from P13's drug-substance-only `substance_info`: the
    excipient axis needed exactly the same treatment, and a second
    parameter for it would have been the second special case.
    """
    repeat_info = repeat_info or {}
    root_node = _Node("ectd:ectd")
    for section_key, leaf in leaves_by_section.items():
        repeated = repeat_info.get(section_key)
        if repeated is not None:
            _place_repeated_leaf(root_node, section_key, leaf, *repeated)
            continue
        # P19: a key may now be "3.2.P.7-pack-blister" as well as a bare
        # number -- packs and manufacturing sites repeat too. A section
        # number never contains a hyphen, so the subject suffix strips
        # cleanly; `_place_drug_substance_leaf` has always split it this
        # way. A Module 1 key (or a "certificate:<uuid>" one) still fails
        # the lookup and is still skipped, which is the intended path.
        path = ICH_HEADING_PATH.get(section_key.split("-", 1)[0])
        if path is None:
            continue
        node = root_node
        for tag in path[:-1]:
            node = node.child(tag)
        node.child(path[-1]).leaves.append(leaf)

    root = etree.Element(f"{{{ECTD_NS}}}ectd", nsmap={"ectd": ECTD_NS})
    root.set("dtd-version", "3.2")
    _attach(root, root_node)

    xml_bytes = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
        doctype='<!DOCTYPE ectd:ectd SYSTEM "util/dtd/ich-ectd-3-2.dtd">',
    )

    dtd = etree.DTD(str(DTD_PATH))
    parsed = etree.fromstring(xml_bytes)
    if not dtd.validate(parsed):
        raise ValueError(f"index.xml failed DTD validation: {dtd.error_log}")

    return xml_bytes
