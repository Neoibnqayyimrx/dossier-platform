"""EU regional backbone (`m1/eu/eu-regional.xml`) builder (P09).

WHY Module 1 lives ENTIRELY here, not in `app.ectd.index_xml`: confirmed
from the real DTDs (reference/ectd_dtd/) that the ICH backbone's own M1
element is a flat, structure-less `(leaf*)` bag -- the real Module 1
hierarchy (`m1-0-cover`, `m1-2-form`, `m1-3-pi`, ...) is entirely the
regional DTD's doing. This mirrors how real eCTD submissions are authored:
one backbone per concern, not one backbone that knows everything.

WHY certificates/declarations fold into `m1-2-form`, not their own
elements: `eu-regional.dtd` has no dedicated element for either -- past
`m1-2-form (specific+)`, the DTD only offers an unstructured `specific`
wrapper holding `(leaf | node-extension)*`. Real EU filers bundle GMP
certificates, POAs etc. as annexes to the application form for exactly
this reason. We use the DTD's own `node-extension` element (a generic
titled sub-group) to keep Certificates and Declarations visually distinct
inside that one bucket, without inventing DTD structure that doesn't exist.

WHY the envelope constants below (agency/procedure/country) are hardcoded
rather than per-Project fields: a real EU submission's choice of agency
(which member state, or EMA-centralised) and procedure type is genuinely
per-project data `Project` doesn't model yet -- the same category of scope
edge P04 hit with QOS and P08 hit with labeling artwork. Baking in one
concrete, valid choice keeps the envelope real and DTD-valid without
inventing config this phase's own scope (checksums, DTD structure,
lifecycle) doesn't require solving. Flagged in the P09 build-log entry as
a documented limitation, not silently decided.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from app.ectd.leaf import Leaf, XLINK_NS, build_leaf_element
from app.models.enums import RegistrationType
from app.models.project import Project

EU_NS = "http://europa.eu.int"
# Shared with app.ectd.backbone (where the file gets written) and
# app.ectd.validate (P10, where it gets re-read and re-checked) -- one
# constant instead of the same string literal in three places.
REGIONAL_XML_RELATIVE_PATH = "m1/eu/eu-regional.xml"
DTD_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "reference"
    / "ectd_dtd"
    / "eu-regional.dtd"
)

# --- MVP envelope defaults -- see module docstring's WHY -----------------
_AGENCY_CODE = "DE-BFARM"
_ENVELOPE_COUNTRY = "de"
_PROCEDURE_TYPE = "national"
_DOCUMENT_COUNTRY = "common"  # `specific`/leaf docs not tied to one member state
_SUBMISSION_UNIT_TYPE = "initial"  # always -- procedural correspondence types are out of scope

_SUBMISSION_TYPE_BY_REGISTRATION_TYPE: dict[RegistrationType, str] = {
    RegistrationType.NEW: "maa",
    RegistrationType.RENEWAL: "renewal",
    RegistrationType.VARIATION: "var-nat",
}


def _submission_type(project: Project) -> str:
    registration_type = project.product.registration_type
    if registration_type is None:
        # DTD requires a value; "maa" (a fresh application) is the honest
        # default for "not yet decided" rather than silently guessing
        # renewal/variation.
        return "maa"
    return _SUBMISSION_TYPE_BY_REGISTRATION_TYPE[registration_type]


def _build_envelope(
    project: Project, sequence_number: str, related_sequence_numbers: list[str]
) -> etree._Element:
    envelope_root = etree.Element("eu-envelope")
    envelope = etree.SubElement(envelope_root, "envelope")
    envelope.set("country", _ENVELOPE_COUNTRY)

    identifier = etree.SubElement(envelope, "identifier")
    identifier.text = str(project.id)

    submission = etree.SubElement(envelope, "submission")
    submission.set("type", _submission_type(project))
    tracking = etree.SubElement(submission, "procedure-tracking")
    number = etree.SubElement(tracking, "number")
    # Honest placeholder, not a fabricated regulatory number -- Project
    # has no field yet for a real EMA/member-state procedure number (same
    # "placeholder, never fabricated content" rule as
    # app.templating.certificates).
    number.text = "PENDING-PROCEDURE-NUMBER"

    submission_unit = etree.SubElement(envelope, "submission-unit")
    submission_unit.set("type", _SUBMISSION_UNIT_TYPE)

    applicant = etree.SubElement(envelope, "applicant")
    applicant.text = project.applicant.company_name if project.applicant else "UNKNOWN APPLICANT"

    agency = etree.SubElement(envelope, "agency")
    agency.set("code", _AGENCY_CODE)

    procedure = etree.SubElement(envelope, "procedure")
    procedure.set("type", _PROCEDURE_TYPE)

    invented_name = etree.SubElement(envelope, "invented-name")
    invented_name.text = project.product.brand_name

    for api in project.product.apis:
        inn = etree.SubElement(envelope, "inn")
        inn.text = api.inn_name

    sequence_el = etree.SubElement(envelope, "sequence")
    sequence_el.text = sequence_number

    for related in related_sequence_numbers:
        related_el = etree.SubElement(envelope, "related-sequence")
        related_el.text = related

    description = etree.SubElement(envelope, "submission-description")
    description.text = (
        f"{_submission_type(project).upper()} submission for {project.product.brand_name}"
    )

    return envelope_root


def _build_specific(country: str, leaves: list[Leaf]) -> etree._Element:
    specific = etree.Element("specific", nsmap={"xlink": XLINK_NS})
    specific.set("country", country)
    for leaf in leaves:
        specific.append(build_leaf_element(leaf))
    return specific


def _build_node_extension(group_id: str, title: str, leaves: list[Leaf]) -> etree._Element:
    node = etree.Element("node-extension", nsmap={"xlink": XLINK_NS})
    node.set("ID", group_id)
    title_el = etree.SubElement(node, "title")
    title_el.text = title
    for leaf in leaves:
        node.append(build_leaf_element(leaf))
    return node


def build_regional_xml(
    project: Project,
    sequence_number: str,
    related_sequence_numbers: list[str],
    leaves_by_slot: dict[str, list[Leaf]],
) -> bytes:
    """Build and DTD-validate `eu-regional.xml`.

    `leaves_by_slot` keys match `app.ctd.region_profiles.EU_PROFILE`'s
    `Module1Slot.slot_id`s: "cover-letter" and "registration-form" hold at
    most one leaf each; "certificates"/"declarations" can hold several,
    each folded into `m1-2-form` as its own titled `node-extension`.
    """
    root = etree.Element(f"{{{EU_NS}}}eu-backbone", nsmap={"eu": EU_NS, "xlink": XLINK_NS})
    root.set("dtd-version", "3.1")

    root.append(_build_envelope(project, sequence_number, related_sequence_numbers))

    m1_eu = etree.SubElement(root, "m1-eu")

    # `m1-0-cover` is the ONE m1-eu child the DTD marks mandatory (no `?`
    # on it, unlike every other m1-eu child) -- it must appear in every
    # sequence's regional backbone even when this sequence's lifecycle
    # resolver found nothing new about the cover letter (real EU filers
    # sidestep this because a cover letter is per-submission correspondence
    # that's inherently always fresh; ours doesn't vary cover-letter
    # content by sequence number yet, which would need threading `Sequence`
    # into P04's renderer -- out of scope here). The DTD's own
    # `specific+` content model permits an empty `specific` wrapper, so an
    # unchanged cover letter still produces valid (if contentless) XML
    # here rather than an invalid document.
    m1_0_cover = etree.SubElement(m1_eu, "m1-0-cover")
    m1_0_cover.append(_build_specific(_DOCUMENT_COUNTRY, leaves_by_slot.get("cover-letter", [])))

    form_leaves = leaves_by_slot.get("registration-form", [])
    certificate_leaves = leaves_by_slot.get("certificates", [])
    declaration_leaves = leaves_by_slot.get("declarations", [])
    if form_leaves or certificate_leaves or declaration_leaves:
        m1_2_form = etree.SubElement(m1_eu, "m1-2-form")
        specific = etree.SubElement(m1_2_form, "specific", nsmap={"xlink": XLINK_NS})
        specific.set("country", _DOCUMENT_COUNTRY)
        for leaf in form_leaves:
            specific.append(build_leaf_element(leaf))
        if certificate_leaves:
            specific.append(
                _build_node_extension(
                    f"GRP-certificates-{sequence_number}", "Certificates", certificate_leaves
                )
            )
        if declaration_leaves:
            specific.append(
                _build_node_extension(
                    f"GRP-declarations-{sequence_number}", "Declarations", declaration_leaves
                )
            )

    xml_bytes = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
        doctype='<!DOCTYPE eu:eu-backbone SYSTEM "util/dtd/eu-regional.dtd">',
    )

    dtd = etree.DTD(str(DTD_PATH))
    parsed = etree.fromstring(xml_bytes)
    if not dtd.validate(parsed):
        raise ValueError(f"eu-regional.xml failed DTD validation: {dtd.error_log}")

    return xml_bytes
