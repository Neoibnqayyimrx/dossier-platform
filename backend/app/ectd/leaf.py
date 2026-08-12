"""Leaf model -> `<leaf>` element (P09).

WHY the deterministic `ID` scheme (`ID-<section-slug>-<sequence-number>`),
not a random/UUID one: two requirements point the same way. (1) Golden-
fixture byte-stability -- the same inputs must produce byte-identical
`index.xml` every time (AGENTS.md §5's idempotent-builders rule), which
rules out anything random. (2) The lifecycle resolver
(`app.ectd.lifecycle`) needs to compute what a document's ID *was* in a
prior sequence -- the value `modified-file` must reference on a `replace`
-- purely from `section_key` + that old sequence's number, with no lookup
table. A deterministic scheme makes that a pure function instead of a
join.

WHY lxml's real namespace API (`nsmap=`/Clark notation), not literal
colon-in-string attribute names: tried the literal-string route first --
`element.set("xlink:href", ...)` -- expecting it to match the DTD's
namespace-unaware, colon-in-the-literal-name declarations. lxml rejects it
outright (`ValueError: Invalid attribute name`); it treats any colon as a
namespace prefix and requires a real binding. Verified empirically that
building elements the *proper* lxml way (`nsmap={"xlink": XLINK_NS}`,
`el.set("{%s}href" % XLINK_NS, ...)`) round-trips through
`tostring()`/`fromstring()` into exactly the same `xlink:href="..."` text
a hand-authored eCTD file has, and validates cleanly against
`ich-ectd-3-2.dtd` -- libxml2's DTD validator matches the serialized
qualified name, not the construction method. So: real namespaces in, real
namespaces out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

# A real, documented quirk of the ICH eCTD 3.2 DTD itself: its #FIXED
# xlink namespace URI is misspelled "w3c.org" (the real xlink namespace is
# w3.org). Reproduced verbatim -- DTD validation checks a #FIXED attribute
# for an exact string match, so "correcting" the typo would make our own
# output DTD-invalid against the DTD we're actually validating against.
XLINK_NS = "http://www.w3c.org/1999/xlink"

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def slugify_section_key(section_key: str) -> str:
    """"3.2.P.1" -> "3-2-P-1"; "cover-letter" -> "cover-letter"."""
    return _SLUG_RE.sub("-", section_key).strip("-")


def leaf_id_for(section_key: str, sequence_number: str) -> str:
    """The deterministic `ID` a leaf for `section_key` gets in sequence
    `sequence_number`. Prefixed with a letter ("ID-") because XML's ID
    token may not start with a digit, and every `section_key` we use
    (e.g. "3.2.P.1") starts with one."""
    return f"ID-{slugify_section_key(section_key)}-{sequence_number}"


@dataclass(frozen=True)
class Leaf:
    id: str
    title: str
    href: str  # relative to the sequence root, e.g. "m3/32-body-data/.../3.2.P.1.pdf"
    checksum: str  # MD5 hex digest of the file at `href`
    operation: str  # "new" | "replace" | "append" | "delete"
    # Relative-path-into-a-prior-sequence + that leaf's ID (e.g.
    # "../0000/m3/.../3.2.P.1.pdf#ID-3-2-P-1-0000"). Required by the DTD
    # for anything except "new" -- see `build_leaf_element`.
    modified_file: str | None = None


def build_leaf_element(leaf: Leaf) -> etree._Element:
    if leaf.operation != "new" and not leaf.modified_file:
        raise ValueError(
            f"leaf {leaf.id!r}: operation={leaf.operation!r} requires modified_file "
            "(the DTD only leaves it IMPLIED, but a replace/append/delete with nothing "
            "to point at is a modeling bug, not a valid document)"
        )

    el = etree.Element("leaf", nsmap={"xlink": XLINK_NS})
    el.set("ID", leaf.id)
    el.set("operation", leaf.operation)
    if leaf.modified_file:
        el.set("modified-file", leaf.modified_file)
    el.set("checksum", leaf.checksum)
    el.set("checksum-type", "md5")
    el.set(f"{{{XLINK_NS}}}type", "simple")
    el.set(f"{{{XLINK_NS}}}href", leaf.href)

    title_el = etree.SubElement(el, "title")
    title_el.text = leaf.title
    return el
