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

import posixpath
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
    """ "3.2.P.1" -> "3-2-P-1"; "cover-letter" -> "cover-letter"."""
    return _SLUG_RE.sub("-", section_key).strip("-")


def leaf_id_for(section_key: str, sequence_number: str) -> str:
    """The deterministic `ID` a leaf for `section_key` gets in sequence
    `sequence_number`. Prefixed with a letter ("ID-") because XML's ID
    token may not start with a digit, and every `section_key` we use
    (e.g. "3.2.P.1") starts with one."""
    return f"ID-{slugify_section_key(section_key)}-{sequence_number}"


_SEQUENCE_SUFFIX_RE = re.compile(r"-(\d{4})$")


def sequence_number_of(leaf_id: str) -> str:
    """The sequence a leaf ID was issued in -- the inverse of `leaf_id_for`.

    WHY this exists (gap Phase 4a): `modified-file` must name the sequence
    whose backbone actually CONTAINS the leaf being replaced. The resolver
    used to take that from "the immediately prior sequence", which is only
    right when the document changed in that very sequence. A document left
    untouched in 0001 and replaced in 0002 lives in 0000's backbone, not
    0001's -- and was being pointed at 0001. The ID already carries the
    right answer, because the scheme above was made deterministic for
    precisely this kind of lookup.
    """
    match = _SEQUENCE_SUFFIX_RE.search(leaf_id)
    if match is None:
        raise ValueError(f"leaf ID {leaf_id!r} was not issued by leaf_id_for")
    return match.group(1)


@dataclass(frozen=True)
class Leaf:
    id: str
    title: str
    # Relative to the SEQUENCE ROOT, e.g. "m3/32-body-data/.../3.2.P.1.pdf",
    # whichever backbone file the leaf ends up in -- `build_leaf_element`
    # re-expresses it relative to that file. None only for `delete`: there
    # is no file, and the DTD leaves xlink:href IMPLIED.
    href: str | None
    # MD5 hex digest of the file at `href`; "" for `delete`, which the ICH
    # spec (v3.2.2, Appendix 6) states outright: "the checksum attribute
    # value will be empty".
    checksum: str
    operation: str  # "new" | "replace" | "append" | "delete"
    # The ID of the earlier leaf this one replaces/appends to/deletes.
    # Required for anything except "new" -- see `build_leaf_element`.
    #
    # WHY an ID and not a ready-made `modified-file` string: the ICH spec
    # says modified-file "points to the index.xml file and the leaf ID"
    # (e.g. "../0001/index.xml#a1234567") -- i.e. to a BACKBONE FILE, and to
    # the same backbone this leaf sits in. The resolver that decides the
    # operation cannot know which backbone that is (index.xml or a regional
    # file, at different depths), so it states only WHAT is modified and
    # the element builder works out WHERE from.
    modifies: str | None = None


def _relative_to(backbone_path: str, sequence_root_path: str) -> str:
    """`sequence_root_path` re-expressed relative to `backbone_path`'s folder.

    WHY: both the ICH spec and FDA's Module 1 spec resolve a leaf's
    xlink:href (and modified-file) from the backbone file's OWN location.
    For index.xml, at the sequence root, that is a no-op; for
    "m1/us/us-regional.xml" it turns "m1/us/cover.pdf" into "cover.pdf"
    and a prior sequence's "../0000/..." into "../../../0000/...". EMA's own
    eu-regional.xsl proves the same for the EU: it renders each leaf as
    `<a href="{@xlink:href}">` inside a page served from m1/eu/.
    """
    folder = posixpath.dirname(backbone_path)
    if not folder:
        return sequence_root_path
    return posixpath.relpath(sequence_root_path, folder)


def build_leaf_element(leaf: Leaf, backbone_path: str = "index.xml") -> etree._Element:
    """One `<leaf>`, for the backbone file at `backbone_path` (relative to
    the sequence root) -- which is what every path in it is relative to."""
    if leaf.operation != "new" and not leaf.modifies:
        raise ValueError(
            f"leaf {leaf.id!r}: operation={leaf.operation!r} requires `modifies` "
            "(the DTD only leaves modified-file IMPLIED, but a replace/append/delete "
            "with nothing to point at is a modeling bug, not a valid document)"
        )
    if leaf.href is None and leaf.operation != "delete":
        raise ValueError(f"leaf {leaf.id!r}: only a delete may have no file")

    el = etree.Element("leaf", nsmap={"xlink": XLINK_NS})
    el.set("ID", leaf.id)
    el.set("operation", leaf.operation)
    if leaf.modifies:
        # The same backbone file, in the sequence that issued the target ID.
        target = f"../{sequence_number_of(leaf.modifies)}/{backbone_path}"
        el.set("modified-file", f"{_relative_to(backbone_path, target)}#{leaf.modifies}")
    el.set("checksum", leaf.checksum)
    el.set("checksum-type", "md5")
    el.set(f"{{{XLINK_NS}}}type", "simple")
    if leaf.href is not None:
        el.set(f"{{{XLINK_NS}}}href", _relative_to(backbone_path, leaf.href))

    title_el = etree.SubElement(el, "title")
    title_el.text = leaf.title
    return el
