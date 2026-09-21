"""Mechanical eCTD checks (P10): re-validate a BUILT sequence's zip
artifact -- a different thing from P06, which validates the project's
DATA before anything is ever rendered. P06 can pass while the artifact
P09 produced is still broken (a storage bug, tampering, a bug in P09
itself) -- this layer re-checks the actual package, not the data behind it.

Every function here is pure: given already-extracted zip contents (plain
`{path: bytes}` dicts, exactly what `zipfile.namelist()`/`.read()` give
you), no storage/DB access. `app.ectd.report` does the I/O (fetching this
sequence's zip and any prior sequences' zips from storage) and calls these.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

from lxml import etree
from pypdf import PdfReader
import io

from app.ectd import us_regional
from app.ectd.backbone import REGIONAL_BACKBONES
from app.ectd.checksum import md5_hex
from app.ectd.index_xml import DTD_PATH as ICH_DTD_PATH
from app.ectd.leaf import XLINK_NS
from app.templating.registry import SECTIONS
from app.validation.engine import Finding, Severity

SOURCE = "mechanical-ectd"

# A modified-file value, once resolved against the folder of the backbone
# file it appears in, must name "<sequence>/<a backbone file>" -- e.g.
# "0000/index.xml" or "0000/m1/eu/eu-regional.xml". See `_resolve`.
_BACKBONE_TARGET_RE = re.compile(r"^(?P<sequence>\d{4})/(?P<backbone>[^#]+\.xml)$")

_INFRA_PREFIXES = ("index.xml", "index-md5.txt", "util/")

# gap Phase 4c: every regional backbone file this platform can build, keyed
# by where it sits in a sequence. The checks find a package's regional file
# by looking, not by being told the region -- they are pure functions over
# the package's bytes, and the package is what is being judged.
_REGIONAL_DTDS = {rb.relative_path: rb.dtd_path for rb in REGIONAL_BACKBONES.values()}


@dataclass(frozen=True)
class ParsedLeaf:
    id: str
    # Full zip path, WITH the sequence-number prefix -- None for a delete,
    # which carries no file.
    href: str | None
    checksum: str
    operation: str
    modified_file: str | None  # the raw attribute, as written
    backbone: str  # zip path of the backbone file this leaf came from


def _resolve(backbone_path: str, relative: str) -> str:
    """A path written inside `backbone_path`, as a full zip path.

    WHY (gap Phase 4a): every path in a backbone is relative to that
    backbone file's own folder -- ICH and FDA say so, and EMA's stylesheet
    resolves them that way. This used to prepend the sequence prefix
    instead, which only agrees for index.xml, at the sequence root.
    """
    return posixpath.normpath(posixpath.join(posixpath.dirname(backbone_path), relative))


def _parse_leaves(prefix: str, files: dict[str, bytes]) -> list[ParsedLeaf]:
    """Every `<leaf>` across `index.xml` and whichever regional backbone
    the package has, with hrefs resolved to full zip-relative paths."""
    leaves: list[ParsedLeaf] = []
    for rel_path in ("index.xml", *_REGIONAL_DTDS):
        backbone_path = f"{prefix}/{rel_path}"
        xml_bytes = files.get(backbone_path)
        if xml_bytes is None:
            continue
        root = etree.fromstring(xml_bytes)
        for el in root.findall(".//leaf"):
            href = el.get(f"{{{XLINK_NS}}}href")
            leaves.append(
                ParsedLeaf(
                    id=el.get("ID"),
                    href=_resolve(backbone_path, href) if href is not None else None,
                    checksum=el.get("checksum"),
                    operation=el.get("operation"),
                    modified_file=el.get("modified-file"),
                    backbone=backbone_path,
                )
            )
    return leaves


def check_dtd_validity(prefix: str, files: dict[str, bytes]) -> list[Finding]:
    findings: list[Finding] = []
    index_xml = files.get(f"{prefix}/index.xml")
    if index_xml is not None:
        dtd = etree.DTD(str(ICH_DTD_PATH))
        if not dtd.validate(etree.fromstring(index_xml)):
            findings.append(
                Finding(
                    rule_id="M01",
                    severity=Severity.ERROR,
                    category="dtd",
                    message=f"index.xml failed DTD validation: {dtd.error_log}",
                    source=SOURCE,
                )
            )
    # M02 is "the regional backbone is valid against ITS region's DTD" --
    # EU's since P10, and FDA's since gap Phase 4c. Before that it was
    # hard-wired to eu-regional.xml, so an FDA package's Module 1 backbone
    # would have gone unchecked without anything saying so.
    for rel_path, dtd_path in _REGIONAL_DTDS.items():
        regional_xml = files.get(f"{prefix}/{rel_path}")
        if regional_xml is None:
            continue
        dtd = etree.DTD(str(dtd_path))
        if not dtd.validate(etree.fromstring(regional_xml)):
            findings.append(
                Finding(
                    rule_id="M02",
                    severity=Severity.ERROR,
                    category="dtd",
                    message=(
                        f"{posixpath.basename(rel_path)} failed DTD validation against "
                        f"{dtd_path.name}: {dtd.error_log}"
                    ),
                    source=SOURCE,
                )
            )
    return findings


def check_checksum_integrity(prefix: str, files: dict[str, bytes]) -> list[Finding]:
    """Every leaf's stated checksum matches the ACTUAL file's MD5, and
    `index-md5.txt` matches the ACTUAL `index.xml` bytes. Leaves whose
    file is entirely missing are left to `check_href_resolution` -- one
    root cause, one finding, not two."""
    findings: list[Finding] = []
    for leaf in _parse_leaves(prefix, files):
        if leaf.href is None:
            continue  # a delete: no file, and an empty checksum by spec
        data = files.get(leaf.href)
        if data is None:
            continue
        actual = md5_hex(data)
        if actual != leaf.checksum:
            findings.append(
                Finding(
                    rule_id="M03",
                    severity=Severity.ERROR,
                    category="checksum",
                    message=(
                        f"leaf {leaf.id!r} ({leaf.href}) states checksum {leaf.checksum} "
                        f"but the actual file's MD5 is {actual}"
                    ),
                    source=SOURCE,
                )
            )

    index_xml = files.get(f"{prefix}/index.xml")
    index_md5_txt = files.get(f"{prefix}/index-md5.txt")
    if index_xml is not None and index_md5_txt is not None:
        actual = md5_hex(index_xml)
        if actual not in index_md5_txt.decode():
            findings.append(
                Finding(
                    rule_id="M04",
                    severity=Severity.ERROR,
                    category="checksum",
                    message=(
                        f"index-md5.txt does not match index.xml's actual MD5 "
                        f"(expected {actual})"
                    ),
                    source=SOURCE,
                )
            )
    return findings


def check_href_resolution_and_orphans(prefix: str, files: dict[str, bytes]) -> list[Finding]:
    findings: list[Finding] = []
    leaves = _parse_leaves(prefix, files)
    referenced = {leaf.href for leaf in leaves if leaf.href is not None}

    for leaf in leaves:
        if leaf.href is not None and leaf.href not in files:
            findings.append(
                Finding(
                    rule_id="M05",
                    severity=Severity.ERROR,
                    category="structure",
                    message=f"leaf {leaf.id!r} points at {leaf.href}, which is not in the package",
                    source=SOURCE,
                )
            )

    for path in files:
        rel = path[len(prefix) + 1 :]
        # The regional backbone used to be exempted here by name, because
        # nothing referenced it. Since gap Phase 4a index.xml does, so an
        # unreferenced regional file is a real finding again.
        if rel.startswith(_INFRA_PREFIXES):
            continue
        if path not in referenced:
            findings.append(
                Finding(
                    rule_id="M06",
                    severity=Severity.WARNING,
                    category="structure",
                    message=f"{path} is in the package but no leaf references it (orphan file)",
                    source=SOURCE,
                )
            )
    return findings


def check_lifecycle_integrity(
    prefix: str, files: dict[str, bytes], prior_files: dict[str, dict[str, bytes]]
) -> list[Finding]:
    """Every `replace`/`append`/`delete` leaf's `modified-file` must name a
    REAL leaf, by ID, inside the same backbone file of an earlier
    sequence's OWN built package -- not just a plausible-looking path.

    The ICH form is "<backbone file of an earlier sequence>#<leaf ID>"
    ("../0001/index.xml#a1234567"), written relative to the backbone the
    leaf itself sits in. Before gap Phase 4a this project wrote the earlier
    DOCUMENT's path instead, and checked for that; such a value now fails
    here as M07, which is the truth about packages built before the fix.
    """
    findings: list[Finding] = []
    for leaf in _parse_leaves(prefix, files):
        if leaf.operation == "new":
            continue
        path, sep, target_id = (leaf.modified_file or "").rpartition("#")
        match = _BACKBONE_TARGET_RE.match(_resolve(leaf.backbone, path)) if sep else None
        if not match or not target_id:
            findings.append(
                Finding(
                    rule_id="M07",
                    severity=Severity.ERROR,
                    category="lifecycle",
                    message=(
                        f"leaf {leaf.id!r} has operation={leaf.operation!r} but "
                        f"modified-file={leaf.modified_file!r} does not name an earlier "
                        f"sequence's backbone file and a leaf ID "
                        f"(expected e.g. '../0000/index.xml#<ID>')"
                    ),
                    source=SOURCE,
                )
            )
            continue

        sequence_number = match.group("sequence")
        target_backbone = match.group(0)
        own_backbone = leaf.backbone[len(prefix) + 1 :]

        prior_bundle = prior_files.get(sequence_number)
        if prior_bundle is None:
            findings.append(
                Finding(
                    rule_id="M08",
                    severity=Severity.ERROR,
                    category="lifecycle",
                    message=(
                        f"leaf {leaf.id!r} targets sequence {sequence_number}, which was "
                        f"never built (or is unavailable) -- modified-file cannot be verified"
                    ),
                    source=SOURCE,
                )
            )
            continue

        # A leaf may only modify a leaf in the same backbone file: the ICH
        # spec has the new leaf submitted "in the same location in the
        # backbone as the leaf element being appended, replaced or deleted".
        prior_ids = {
            pl.id
            for pl in _parse_leaves(sequence_number, prior_bundle)
            if pl.backbone == target_backbone
        }
        if match.group("backbone") != own_backbone or target_id not in prior_ids:
            findings.append(
                Finding(
                    rule_id="M09",
                    severity=Severity.ERROR,
                    category="lifecycle",
                    message=(
                        f"leaf {leaf.id!r} in {own_backbone} has modified-file pointing at "
                        f"leaf {target_id!r} in {target_backbone}, but no such leaf exists "
                        f"in that sequence's {own_backbone}"
                    ),
                    source=SOURCE,
                )
            )
    return findings


def check_pdf_specs(prefix: str, files: dict[str, bytes]) -> list[Finding]:
    """Encryption is a hard, fully-checkable fact (pypdf). Non-empty
    extracted text on page 1 is a PROXY for "text-searchable, not a
    scanned image" -- honest about being a proxy (WARNING, not ERROR).
    Font-embedding is NOT checked here -- a real, documented mechanical-
    check gap, not a silent skip."""
    findings: list[Finding] = []
    for path, data in files.items():
        if not path.endswith(".pdf"):
            continue
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            findings.append(
                Finding(
                    rule_id="M10",
                    severity=Severity.ERROR,
                    category="pdf-spec",
                    message=f"{path} is encrypted -- eCTD PDFs must not be password-protected",
                    source=SOURCE,
                )
            )
            continue
        text = reader.pages[0].extract_text() or ""
        if not text.strip():
            findings.append(
                Finding(
                    rule_id="M11",
                    severity=Severity.WARNING,
                    category="pdf-spec",
                    message=(
                        f"{path}'s first page has no extractable text -- may be a scanned "
                        f"image rather than a text-searchable document"
                    ),
                    source=SOURCE,
                )
            )
    return findings


def check_fda_codes(prefix: str, files: dict[str, bytes]) -> list[Finding]:
    """M13 (gap Phase 4c): every code in an FDA package's us-regional.xml is
    one FDA publishes as "active".

    WHY a check of its own when M02 already validates the file: FDA's DTD
    declares these attributes as bare CDATA, so M02 passes a backbone that
    files an ANDA as `application-type="banana"`. FDA's Module 1 spec
    (v2.6, section I) is explicit that "only coded values with a status of
    'active' should be submitted", and the lists that say which are active
    are separate files FDA versions on their own
    (reference/ectd_dtd/fda-code-lists/). This is the check the DTD cannot
    make.

    WHY it re-reads the built package rather than trusting the builder's
    tables (which tests/test_ectd_fda.py already checks): P10's whole point.
    The package is what reaches FDA; a builder that was right when it ran is
    not evidence about bytes that have since been stored, copied or edited.
    """
    xml_bytes = files.get(f"{prefix}/{us_regional.REGIONAL_XML_RELATIVE_PATH}")
    if xml_bytes is None:
        return []  # not an FDA package
    root = etree.fromstring(xml_bytes)
    findings: list[Finding] = []
    for (element, attribute), list_name in us_regional.CODED_ATTRIBUTES.items():
        published = us_regional.code_list(list_name)
        for el in root.iter(element):
            code = el.get(attribute)
            if code is None:
                continue  # whether it is REQUIRED is M02's question
            status = published.get(code)
            if status == "active":
                continue
            problem = (
                "is not in FDA's list"
                if status is None
                else f"is {status!r}, not 'active', in FDA's list"
            )
            findings.append(
                Finding(
                    rule_id="M13",
                    severity=Severity.ERROR,
                    category="fda-codes",
                    message=(
                        f"us-regional.xml: <{element} {attribute}={code!r}> -- {code!r} "
                        f"{problem} ({list_name}.xml)"
                    ),
                    source=SOURCE,
                )
            )
    return findings


def check_required_ctd_sections_present(
    live_section_keys: set[str], expected_keys: set[str] | None = None
) -> list[Finding]:
    """Every section registered in app.templating.registry.SECTIONS must
    have appeared, live, at least once across the sequence's cumulative
    history. Certificates/declarations are deliberately NOT re-checked
    here -- their presence is already P06's job (R14/R15/R16), at the
    data layer, before anything is ever built; re-litigating it here
    would blur the P06-vs-P10 line this phase exists to keep separate."""
    # P13: what a project OWES is its expanded section instances, not the
    # registry's numbers -- a combination product owes two copies of
    # 3.2.S.1, and "3.2.S.1" itself is never a leaf key. Falls back to the
    # registry for callers that have no project to expand.
    missing = (expected_keys if expected_keys is not None else set(SECTIONS)) - live_section_keys
    return [
        Finding(
            rule_id="M12",
            severity=Severity.ERROR,
            category="completeness",
            message=f"section {key!r} is registered but has never appeared in any built sequence",
            section=key,
            source=SOURCE,
        )
        for key in sorted(missing)
    ]


def run_mechanical_checks(
    prefix: str,
    files: dict[str, bytes],
    prior_files: dict[str, dict[str, bytes]],
    live_section_keys: set[str],
    expected_section_keys: set[str] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    findings += check_dtd_validity(prefix, files)
    findings += check_checksum_integrity(prefix, files)
    findings += check_href_resolution_and_orphans(prefix, files)
    findings += check_lifecycle_integrity(prefix, files, prior_files)
    findings += check_pdf_specs(prefix, files)
    findings += check_required_ctd_sections_present(live_section_keys, expected_section_keys)
    findings += check_fda_codes(prefix, files)
    return findings
