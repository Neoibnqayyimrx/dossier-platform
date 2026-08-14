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
}

# Sections repeated per drug substance: the heading chain BELOW the
# per-substance `m3-2-s-drug-substance` element. That element is inserted
# for us, with its required attributes, by build_index_xml.
DRUG_SUBSTANCE_HEADING_PATH: dict[str, tuple[str, ...]] = {
    "3.2.S.1": ("m3-2-s-1-general-information",),
    "3.2.S.4.1": ("m3-2-s-4-control-of-drug-substance", "m3-2-s-4-1-specification"),
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
    "m3-quality": ("m3-2-body-of-data", "m3-3-literature-references"),
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


def _place_drug_substance_leaf(
    root_node: _Node, section_key: str, leaf: Leaf, info: tuple[str, str]
) -> None:
    """File one 3.2.S leaf under its own `m3-2-s-drug-substance` element.

    `substance` and `manufacturer` are both #REQUIRED by the DTD -- the
    spec refuses to let a drug substance be filed anonymously, since an
    assessor reviewing a combination product must be able to tell whose
    specification they are reading and who made that material.
    """
    substance, manufacturer = info
    number = section_key.split("-", 1)[0]
    try:
        tail = DRUG_SUBSTANCE_HEADING_PATH[number]
    except KeyError:
        raise ValueError(
            f"section {number!r} repeats per drug substance but has no "
            f"DRUG_SUBSTANCE_HEADING_PATH entry"
        )
    body = root_node.child("m3-quality").child("m3-2-body-of-data")
    # discriminator = the substance, so two actives get two sibling elements
    node = body.child(
        "m3-2-s-drug-substance",
        discriminator=substance,
        attrs={"substance": substance, "manufacturer": manufacturer},
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
    substance_info: dict[str, tuple[str, str]] | None = None,
) -> bytes:
    """Build and DTD-validate `index.xml` from this sequence's leaves,
    keyed by `section_key` (an `app.templating.registry.SECTIONS` number).
    Leaves whose `section_key` has no `ICH_HEADING_PATH` entry (Module 1
    documents) are silently skipped here -- they belong only in the
    regional backbone (`app.ectd.regional`).
    """
    substance_info = substance_info or {}
    root_node = _Node("ectd:ectd")
    for section_key, leaf in leaves_by_section.items():
        info = substance_info.get(section_key)
        if info is not None:
            _place_drug_substance_leaf(root_node, section_key, leaf, info)
            continue
        path = ICH_HEADING_PATH.get(section_key)
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
