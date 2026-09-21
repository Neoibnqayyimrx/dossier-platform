"""FDA regional backbone (`m1/us/us-regional.xml`) builder (gap Phase 4b).

The FDA counterpart of `app.ectd.regional` (EU), built against FDA's own
files in reference/ectd_dtd/: `us-regional-v3-3.dtd` for structure, and
FDA's *eCTD Backbone Files Specification for Module 1* v2.6 for everything
the DTD leaves open -- which, for FDA, is most of what matters.

WHY the DTD is not enough on its own here, when it very nearly was for the
EU: FDA's DTD declares almost every admin attribute as bare CDATA. It will
accept `application-type="banana"`. What makes a value legal is its
presence, "active", in FDA's published code lists
(reference/ectd_dtd/fda-code-lists/), so every code below is a named
constant in one table, and tests/test_ectd_fda.py checks each one against
those lists instead of trusting that it was typed correctly. The EU lesson
from Phase 3 -- DTD-valid and wrong is the worst combination available --
applies to FDA at its strongest.

WHY this refuses rather than defaults: the admin block names the applicant
(its D-U-N-S number), the application (the number FDA issued) and the
transaction. None of those is ours to invent, and an empty `<id/>` is
DTD-valid. Rule R34 blocks an FDA export whose data is incomplete; this
module refuses as well, because R34 can be overridden with a logged reason
and a package with a blank application number must not be the result.

Scope, stated: an ORIGINAL APPLICATION and its amendments. Supplements
(CMC, labeling, efficacy -- each its own submission type with its own
effective-date type) are not modelled, and renewal does not exist at FDA.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from lxml import etree

from app.ectd.errors import EctdNotSupportedError
from app.ectd.leaf import Leaf, XLINK_NS, build_leaf_element
from app.models.enums import FDAApplicationType, RegistrationType, SubmissionUnitType
from app.models.project import Project

FDA_NS = "http://www.ich.org/fda"
REGIONAL_XML_RELATIVE_PATH = "m1/us/us-regional.xml"
_REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "reference" / "ectd_dtd"
DTD_PATH = _REFERENCE_DIR / "us-regional-v3-3.dtd"
CODE_LIST_DIR = _REFERENCE_DIR / "fda-code-lists"

# FDA Module 1 spec v2.6, section II: "The header of the Module 1 eCTD
# Backbone File is always the same." Copied from it, including the https
# DOCTYPE (changed from http in spec v2.5). The package still ships a local
# copy under util/dtd/, as ICH v3.2.2 Table 6-2 lists -- the two are not in
# tension: one tells a reader where the standard lives, the other lets the
# package be checked offline.
_DOCTYPE = (
    "<!DOCTYPE fda-regional:fda-regional SYSTEM "
    '"https://www.accessdata.fda.gov/static/eCTD/us-regional-v3-3.dtd">'
)
_STYLESHEET = 'type="text/xsl" href="https://www.accessdata.fda.gov/static/eCTD/us-regional.xsl"'

# ---- FDA's codes --------------------------------------------------------
#
# One table per code list, so tests/test_ectd_fda.py can check every value
# this module can emit against reference/ectd_dtd/fda-code-lists/.

# application-type.xml v1.1
APPLICATION_TYPE_CODES: dict[FDAApplicationType, str] = {
    FDAApplicationType.NDA: "fdaat1",
    FDAApplicationType.ANDA: "fdaat2",
    FDAApplicationType.BLA: "fdaat3",
}
# submission-type.xml v1.3 -- the only regulatory activity modelled.
SUBMISSION_TYPE_ORIGINAL_APPLICATION = "fdast1"
# submission-sub-type.xml v1.1
SUBMISSION_SUB_TYPE_APPLICATION = "fdasst3"
SUBMISSION_SUB_TYPE_AMENDMENT = "fdasst4"
# applicant-contact-type.xml v1.2 -- the contact on file is the regulatory
# one: the person FDA's reviewers write to about this submission.
APPLICANT_CONTACT_TYPE_REGULATORY = "fdaact1"
# telephone-number-type.xml v1.1
TELEPHONE_NUMBER_TYPE_BUSINESS = "fdatnt1"

# Every code this module can write, for the conformance test.
CODES_IN_USE: dict[str, set[str]] = {
    "application-type": set(APPLICATION_TYPE_CODES.values()),
    "submission-type": {SUBMISSION_TYPE_ORIGINAL_APPLICATION},
    "submission-sub-type": {SUBMISSION_SUB_TYPE_APPLICATION, SUBMISSION_SUB_TYPE_AMENDMENT},
    "applicant-contact-type": {APPLICANT_CONTACT_TYPE_REGULATORY},
    "telephone-number-type": {TELEPHONE_NUMBER_TYPE_BUSINESS},
}

# The sequence says what kind of transaction it is in the EU's vocabulary
# (app.models.enums.SubmissionUnitType, P27). FDA's sub-type answers the
# same question for an original application: "application" is the one
# submission that carries the application's primary material, and
# "amendment" is anything that "augment[s] information previously
# submitted. Examples include responses to information requests" (Module 1
# spec v2.6, Table 4). Unit types with no FDA counterpart are absent, and
# refused below rather than guessed.
_SUB_TYPE_BY_UNIT_TYPE: dict[SubmissionUnitType, str] = {
    SubmissionUnitType.INITIAL: SUBMISSION_SUB_TYPE_APPLICATION,
    SubmissionUnitType.RESPONSE: SUBMISSION_SUB_TYPE_AMENDMENT,
    SubmissionUnitType.VALIDATION_RESPONSE: SUBMISSION_SUB_TYPE_AMENDMENT,
    SubmissionUnitType.ADDITIONAL_INFO: SUBMISSION_SUB_TYPE_AMENDMENT,
}

# FDA Module 1 spec v2.6, section III: submission-description "allows up to
# 128 characters. Only the first 128 characters ... will be displayed."
_SUBMISSION_DESCRIPTION_MAX = 128

# ---- Where each Module 1 slot is filed ----------------------------------
#
# (heading path under m1-regional, slot ids filed there), in the ORDER the
# DTD declares those headings. lxml appends in call order and the DTD's
# content models are ordered sequences, so walking this tuple top to bottom
# is what makes the output valid -- the same reason app.ectd.index_xml keeps
# `_CHILD_ORDER`. Keys are `Module1Slot.slot_id`s of FDA_PROFILE.
_PLACEMENT: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("m1-2-cover-letters",), ("cover-letter",)),
    (
        (
            "m1-14-labeling",
            "m1-14-1-draft-labeling",
            "m1-14-1-1-draft-carton-and-container-labels",
        ),
        ("labelling",),
    ),
    (
        ("m1-14-labeling", "m1-14-1-draft-labeling", "m1-14-1-3-draft-labeling-text"),
        # The prescribing information and the patient labeling are both
        # draft labeling TEXT for FDA -- see FDA_PROFILE's note on 1.3.1.
        ("smpc", "patient-information-leaflet"),
    ),
)
PLACED_SLOTS: frozenset[str] = frozenset(slot for _, slots in _PLACEMENT for slot in slots)


def _submission_sub_type(
    submission_unit_type: str, sequence_number: str, first_sequence_number: str
) -> str:
    try:
        sub_type = _SUB_TYPE_BY_UNIT_TYPE[SubmissionUnitType(submission_unit_type)]
    except (KeyError, ValueError):
        raise EctdNotSupportedError(
            f"Sequence {sequence_number} is a {submission_unit_type!r} transaction, which "
            f"has no FDA equivalent for an original application. FDA's sub-types are "
            f"'application' (the first submission) and 'amendment' (everything after it): "
            f"set the sequence's submission_unit_type to 'initial' or 'response'."
        ) from None
    # "There should only be one submission with a sub-type of application
    # within a given submission group" (spec v2.6, Table 4). Every sequence
    # defaults to `initial`, so this is the mistake a filer will actually
    # make, and saying which value to use is the useful answer.
    if sub_type == SUBMISSION_SUB_TYPE_APPLICATION and sequence_number != first_sequence_number:
        raise EctdNotSupportedError(
            f"Sequence {sequence_number} is marked 'initial', but sequence "
            f"{first_sequence_number} already is the original application, and FDA allows "
            f"one 'application' per regulatory activity. Set this sequence's "
            f"submission_unit_type to 'response' (an FDA amendment)."
        )
    return sub_type


def unsupported_reason(project: Project) -> str | None:
    """Why this project's APPLICATION cannot be published to FDA by this
    builder, or None. Rule R35 reports exactly this."""
    registration_type = project.product.registration_type
    if registration_type is RegistrationType.RENEWAL:
        return (
            "FDA has no renewal: US marketing approvals do not expire. Changes to an "
            "approved application are filed as supplements, which are not modelled yet."
        )
    if registration_type is RegistrationType.VARIATION:
        return (
            "An FDA variation is a supplement -- CMC, labeling or efficacy, each with its "
            "own submission type and effective-date type. Supplements are not modelled "
            "yet; FDA publishing covers an original application and its amendments."
        )
    return None


def missing_admin_data(project: Project) -> list[str]:
    """What the admin block needs and the project does not have. Rule R34
    reports exactly this list, so the finding and the refusal cannot
    disagree about what "complete" means."""
    missing: list[str] = []
    applicant = project.applicant
    if applicant is None:
        return ["an applicant"]
    if not applicant.duns_number:
        missing.append("the applicant's D-U-N-S number")
    for label, value in (
        ("a contact name", applicant.contact_name),
        ("a contact telephone number", applicant.contact_phone),
        ("a contact email", applicant.contact_email),
    ):
        if not value:
            missing.append(label)
    if not project.application_number:
        missing.append("the FDA application number")
    if project.fda_application_type is None:
        missing.append("the FDA application type (NDA, ANDA or BLA)")
    return missing


def preflight(
    project: Project,
    sequence_number: str,
    first_sequence_number: str,
    submission_unit_type: str,
) -> str:
    """Everything that can refuse an FDA sequence without building it, and
    the FDA sub-type code if nothing does.

    Called by `app.ectd.build` BEFORE assembly -- so a missing application
    number costs a millisecond rather than a package's worth of LibreOffice
    conversions -- and again by `build_us_regional_xml`, so the builder is
    safe to call on its own.
    """
    reason = unsupported_reason(project)
    if reason is not None:
        raise EctdNotSupportedError(reason + " (rule R35).")
    missing = missing_admin_data(project)
    if missing:
        raise EctdNotSupportedError(
            "Cannot build FDA's Module 1 backbone without " + ", ".join(missing) + " (rule R34)."
        )
    return _submission_sub_type(submission_unit_type, sequence_number, first_sequence_number)


def _admin(
    project: Project, sequence_number: str, first_sequence_number: str, sub_type: str
) -> etree._Element:
    applicant = project.applicant
    admin = etree.Element("admin")

    applicant_info = etree.SubElement(admin, "applicant-info")
    etree.SubElement(applicant_info, "id").text = applicant.duns_number
    etree.SubElement(applicant_info, "company-name").text = applicant.company_name
    kind = "amendment to the original" if sub_type == SUBMISSION_SUB_TYPE_AMENDMENT else "original"
    description = f"{project.fda_application_type.value.upper()} {kind} application for {project.product.brand_name}"
    etree.SubElement(applicant_info, "submission-description").text = description[
        :_SUBMISSION_DESCRIPTION_MAX
    ]

    contacts = etree.SubElement(applicant_info, "applicant-contacts")
    contact = etree.SubElement(contacts, "applicant-contact")
    name = etree.SubElement(contact, "applicant-contact-name")
    name.set("applicant-contact-type", APPLICANT_CONTACT_TYPE_REGULATORY)
    name.text = applicant.contact_name
    telephone = etree.SubElement(etree.SubElement(contact, "telephones"), "telephone")
    telephone.set("telephone-number-type", TELEPHONE_NUMBER_TYPE_BUSINESS)
    telephone.text = applicant.contact_phone
    etree.SubElement(etree.SubElement(contact, "emails"), "email").text = applicant.contact_email

    application_set = etree.SubElement(admin, "application-set")
    application = etree.SubElement(application_set, "application")
    # "For a submission to only one application, this attribute value
    # should be 'true'" (spec v2.6, III.B). Grouped submissions -- one
    # sequence to several applications -- are not modelled.
    application.set("application-containing-files", "true")

    number = etree.SubElement(
        etree.SubElement(application, "application-information"), "application-number"
    )
    number.set("application-type", APPLICATION_TYPE_CODES[project.fda_application_type])
    number.text = project.application_number

    submission = etree.SubElement(application, "submission-information")
    # submission-id is the REGULATORY ACTIVITY, named after its first
    # sequence; sequence-number is this transaction. An amendment in 0003
    # to the original application filed in 0001 carries submission-id 0001
    # -- that is how FDA's review tool groups the two (spec v2.6, III.B.3).
    submission_id = etree.SubElement(submission, "submission-id")
    submission_id.set("submission-type", SUBMISSION_TYPE_ORIGINAL_APPLICATION)
    submission_id.text = first_sequence_number
    sequence = etree.SubElement(submission, "sequence-number")
    sequence.set("submission-sub-type", sub_type)
    sequence.text = sequence_number

    return admin


def _descend(parent: etree._Element, tags: tuple[str, ...]) -> etree._Element:
    """The element at `tags` under `parent`, creating what is missing.

    Reuses an existing element only if it is the LAST child: `_PLACEMENT`
    is in DTD order, so a shared heading (m1-14-labeling) is always the
    most recently appended one when a later path needs it again.
    """
    node = parent
    for tag in tags:
        last = node[-1] if len(node) else None
        node = last if last is not None and last.tag == tag else etree.SubElement(node, tag)
    return node


def build_us_regional_xml(
    project: Project,
    sequence_number: str,
    first_sequence_number: str,
    leaves_by_slot: dict[str, list[Leaf]],
    submission_unit_type: str = SubmissionUnitType.INITIAL.value,
) -> bytes:
    """Build and DTD-validate `us-regional.xml` for one sequence.

    `leaves_by_slot` is keyed by FDA_PROFILE's `Module1Slot.slot_id`s.
    `first_sequence_number` is the first sequence of the regulatory
    activity -- the original application -- and becomes `submission-id`.
    """
    sub_type = preflight(project, sequence_number, first_sequence_number, submission_unit_type)
    unplaceable = {slot for slot, leaves in leaves_by_slot.items() if leaves} - PLACED_SLOTS
    if unplaceable:
        # A config error, not a filer's: FDA_PROFILE has a slot this module
        # has no heading for. Dropping its documents silently would leave
        # files in the package that the backbone never mentions.
        raise ValueError(f"No FDA Module 1 heading for slot(s) {sorted(unplaceable)}")

    root = etree.Element(
        f"{{{FDA_NS}}}fda-regional", nsmap={"fda-regional": FDA_NS, "xlink": XLINK_NS}
    )
    root.set("dtd-version", "3.3")
    root.append(_admin(project, sequence_number, first_sequence_number, sub_type))

    # "Only include the section headings that reference files in the
    # submission ... Empty section headings should not be included" (spec
    # v2.6, Introduction). m1-regional is itself optional in the DTD, so a
    # sequence that changes nothing in Module 1 has none.
    placed = [
        (path, [leaf for slot in slots for leaf in leaves_by_slot.get(slot, [])])
        for path, slots in _PLACEMENT
    ]
    if any(leaves for _, leaves in placed):
        m1_regional = etree.SubElement(root, "m1-regional")
        for path, leaves in placed:
            if not leaves:
                continue
            heading = _descend(m1_regional, path)
            for leaf in leaves:
                if path == ("m1-2-cover-letters",):
                    # FDA's conformance guide asks for the sequence number
                    # or a date in every cover letter's leaf title, so a
                    # reviewer can tell one sequence's letter from another's.
                    leaf = replace(leaf, title=f"{leaf.title} {sequence_number}")
                heading.append(build_leaf_element(leaf, REGIONAL_XML_RELATIVE_PATH))

    root.addprevious(etree.PI("xml-stylesheet", _STYLESHEET))
    xml_bytes = etree.tostring(
        root.getroottree(),
        xml_declaration=True,
        encoding="UTF-8",
        standalone=False,
        pretty_print=True,
        doctype=_DOCTYPE,
    )

    dtd = etree.DTD(str(DTD_PATH))
    if not dtd.validate(etree.fromstring(xml_bytes)):
        raise ValueError(f"us-regional.xml failed DTD validation: {dtd.error_log}")
    return xml_bytes
