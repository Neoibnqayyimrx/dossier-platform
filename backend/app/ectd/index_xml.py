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
    __slots__ = ("tag", "children", "leaves")

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.children: dict[str, "_Node"] = {}
        self.leaves: list[Leaf] = []

    def child(self, tag: str) -> "_Node":
        if tag not in self.children:
            self.children[tag] = _Node(tag)
        return self.children[tag]


def _attach(el: etree._Element, node: _Node) -> None:
    """Fill already-created element `el` with `node`'s leaves (first,
    per every heading's `leaf*` prefix in its content model) then its
    child headings, in real DTD-declared order."""
    for leaf in node.leaves:
        el.append(build_leaf_element(leaf))

    order = _CHILD_ORDER.get(node.tag)
    if order is None:
        child_tags = list(node.children)
    else:
        unknown = set(node.children) - set(order)
        if unknown:
            raise ValueError(
                f"{node.tag}: no declared DTD order for child(ren) {sorted(unknown)} -- "
                "add them to _CHILD_ORDER before registering a section that uses them"
            )
        child_tags = [t for t in order if t in node.children]

    for tag in child_tags:
        child_el = etree.SubElement(el, tag)
        _attach(child_el, node.children[tag])


def build_index_xml(leaves_by_section: dict[str, Leaf]) -> bytes:
    """Build and DTD-validate `index.xml` from this sequence's leaves,
    keyed by `section_key` (an `app.templating.registry.SECTIONS` number).
    Leaves whose `section_key` has no `ICH_HEADING_PATH` entry (Module 1
    documents) are silently skipped here -- they belong only in the
    regional backbone (`app.ectd.regional`).
    """
    root_node = _Node("ectd:ectd")
    for section_key, leaf in leaves_by_section.items():
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
