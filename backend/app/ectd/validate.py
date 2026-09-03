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

import re
from dataclasses import dataclass

from lxml import etree
from pypdf import PdfReader
import io

from app.ectd.checksum import md5_hex
from app.ectd.index_xml import DTD_PATH as ICH_DTD_PATH
from app.ectd.leaf import XLINK_NS
from app.ectd.regional import DTD_PATH as EU_DTD_PATH, REGIONAL_XML_RELATIVE_PATH
from app.templating.registry import SECTIONS
from app.validation.engine import Finding, Severity

SOURCE = "mechanical-ectd"

# "../0000/m3/.../3.2.P.1.pdf#ID-3-2-P-1-0000" -> full_path is captured
# WITH the sequence-number prefix, so it's directly usable as a dict key
# into a `{path: bytes}` bundle -- no reassembly needed by callers.
_MODIFIED_FILE_RE = re.compile(r"^\.\./(?P<full_path>(?P<sequence>\d{4})/.+)#(?P<leaf_id>[^#]+)$")

_INFRA_PREFIXES = ("index.xml", "index-md5.txt", "util/")


@dataclass(frozen=True)
class ParsedLeaf:
    id: str
    href: str  # full path, WITH the sequence-number prefix
    checksum: str
    operation: str
    modified_file: str | None
    backbone: str  # "index" | "regional" -- which file this leaf came from


def _parse_leaves(prefix: str, files: dict[str, bytes]) -> list[ParsedLeaf]:
    """Every `<leaf>` across `index.xml` and (if present) the EU regional
    backbone, with hrefs resolved to full zip-relative paths."""
    leaves: list[ParsedLeaf] = []
    for backbone_name, rel_path in (
        ("index", "index.xml"),
        ("regional", REGIONAL_XML_RELATIVE_PATH),
    ):
        xml_bytes = files.get(f"{prefix}/{rel_path}")
        if xml_bytes is None:
            continue
        root = etree.fromstring(xml_bytes)
        for el in root.findall(".//leaf"):
            href = el.get(f"{{{XLINK_NS}}}href")
            leaves.append(
                ParsedLeaf(
                    id=el.get("ID"),
                    href=f"{prefix}/{href}",
                    checksum=el.get("checksum"),
                    operation=el.get("operation"),
                    modified_file=el.get("modified-file"),
                    backbone=backbone_name,
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
    regional_xml = files.get(f"{prefix}/{REGIONAL_XML_RELATIVE_PATH}")
    if regional_xml is not None:
        dtd = etree.DTD(str(EU_DTD_PATH))
        if not dtd.validate(etree.fromstring(regional_xml)):
            findings.append(
                Finding(
                    rule_id="M02",
                    severity=Severity.ERROR,
                    category="dtd",
                    message=f"eu-regional.xml failed DTD validation: {dtd.error_log}",
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
    referenced = {leaf.href for leaf in _parse_leaves(prefix, files)}

    for leaf in _parse_leaves(prefix, files):
        if leaf.href not in files:
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
        if rel.startswith(_INFRA_PREFIXES) or rel == REGIONAL_XML_RELATIVE_PATH:
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
    """Every `replace`/`append`/`delete` leaf's `modified-file` must
    resolve to a REAL leaf, with a matching ID, inside the prior
    sequence's OWN built package -- not just a plausible-looking path."""
    findings: list[Finding] = []
    for leaf in _parse_leaves(prefix, files):
        if leaf.operation == "new":
            continue
        match = _MODIFIED_FILE_RE.match(leaf.modified_file or "")
        if not match:
            findings.append(
                Finding(
                    rule_id="M07",
                    severity=Severity.ERROR,
                    category="lifecycle",
                    message=(
                        f"leaf {leaf.id!r} has operation={leaf.operation!r} but an "
                        f"unparseable modified-file={leaf.modified_file!r}"
                    ),
                    source=SOURCE,
                )
            )
            continue

        sequence_number = match.group("sequence")
        full_path = match.group("full_path")
        target_id = match.group("leaf_id")

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

        prior_leaves = {pl.id: pl for pl in _parse_leaves(sequence_number, prior_bundle)}
        target = prior_leaves.get(target_id)
        if target is None or target.href != full_path:
            findings.append(
                Finding(
                    rule_id="M09",
                    severity=Severity.ERROR,
                    category="lifecycle",
                    message=(
                        f"leaf {leaf.id!r}'s modified-file points at leaf {target_id!r}/"
                        f"{full_path} in sequence {sequence_number}, but no such leaf exists there"
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
    return findings
