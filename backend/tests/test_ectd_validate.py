"""Tests for the P10 mechanical eCTD checks (app.ectd.validate) and the
external validator adapter (app.ectd.external_validator) -- all pure
functions over plain `{path: bytes}` dicts, no DB/storage needed. Each
check gets a deliberately corrupted fixture proving it actually catches
the fault, plus the clean case proving it doesn't false-positive.
"""

from __future__ import annotations

import io

from pypdf import PdfWriter

from app.ectd.checksum import md5_hex
from app.ectd.external_validator import NullExternalValidator
from app.ectd.leaf import XLINK_NS, leaf_id_for
from app.ectd.validate import (
    check_checksum_integrity,
    check_dtd_validity,
    check_href_resolution_and_orphans,
    check_lifecycle_integrity,
    check_pdf_specs,
    check_required_ctd_sections_present,
)
from app.validation.engine import Severity


def _leaf_xml(
    leaf_id: str, href: str, checksum: str, operation: str = "new", modified_file: str | None = None
) -> str:
    mf = f' modified-file="{modified_file}"' if modified_file else ""
    return (
        f'<leaf xmlns:xlink="{XLINK_NS}" ID="{leaf_id}" operation="{operation}"{mf} '
        f'checksum="{checksum}" checksum-type="md5" xlink:type="simple" xlink:href="{href}">'
        f"<title>t</title></leaf>"
    )


def _index_xml(*leaves_xml: str) -> bytes:
    body = "".join(leaves_xml)
    return (
        f'<ectd:ectd xmlns:ectd="http://www.ich.org/ectd" dtd-version="3.2">'
        f"<m3-quality><m3-2-body-of-data><m3-2-p-drug-product>"
        f"<m3-2-p-1-description-and-composition-of-the-drug-product>{body}"
        f"</m3-2-p-1-description-and-composition-of-the-drug-product>"
        f"</m3-2-p-drug-product></m3-2-body-of-data></m3-quality></ectd:ectd>"
    ).encode()


# ---- check_dtd_validity -----------------------------------------------------


def test_dtd_validity_passes_a_real_document():
    pdf = b"%PDF-1.4 fake"
    leaf = _leaf_xml(leaf_id_for("3.2.P.1", "0000"), "m3/x.pdf", md5_hex(pdf))
    files = {"0000/index.xml": _index_xml(leaf), "0000/m3/x.pdf": pdf}
    assert check_dtd_validity("0000", files) == []


def test_dtd_validity_catches_a_structurally_invalid_document():
    # m3-quality directly under root with no m3-2-body-of-data wrapper --
    # violates the DTD's declared content model.
    bad_xml = (
        b'<ectd:ectd xmlns:ectd="http://www.ich.org/ectd" dtd-version="3.2">'
        b"<m3-quality><not-a-real-child/></m3-quality></ectd:ectd>"
    )
    findings = check_dtd_validity("0000", {"0000/index.xml": bad_xml})
    assert [f.rule_id for f in findings] == ["M01"]
    assert findings[0].severity == Severity.ERROR


# ---- check_checksum_integrity ----------------------------------------------


def test_checksum_integrity_catches_a_tampered_file():
    pdf = b"%PDF-1.4 original"
    correct_md5 = md5_hex(pdf)
    leaf = _leaf_xml(leaf_id_for("3.2.P.1", "0000"), "m3/x.pdf", correct_md5)
    files = {"0000/index.xml": _index_xml(leaf), "0000/m3/x.pdf": pdf + b"\x00tampered"}

    findings = check_checksum_integrity("0000", files)
    assert [f.rule_id for f in findings] == ["M03"]
    assert correct_md5 in findings[0].message


def test_checksum_integrity_catches_a_bad_index_md5_txt():
    pdf = b"%PDF-1.4 x"
    leaf = _leaf_xml(leaf_id_for("3.2.P.1", "0000"), "m3/x.pdf", md5_hex(pdf))
    index_xml = _index_xml(leaf)
    files = {
        "0000/index.xml": index_xml,
        "0000/m3/x.pdf": pdf,
        "0000/index-md5.txt": b"deadbeef  index.xml\n",
    }
    findings = check_checksum_integrity("0000", files)
    assert [f.rule_id for f in findings] == ["M04"]


# ---- check_href_resolution_and_orphans -------------------------------------


def test_href_resolution_catches_a_dangling_reference():
    leaf = _leaf_xml(leaf_id_for("3.2.P.1", "0000"), "m3/missing.pdf", "a" * 32)
    findings = check_href_resolution_and_orphans("0000", {"0000/index.xml": _index_xml(leaf)})
    assert [f.rule_id for f in findings] == ["M05"]


def test_href_resolution_catches_an_orphan_file():
    files = {
        "0000/index.xml": _index_xml(),
        "0000/m3/stray.pdf": b"%PDF-1.4 unreferenced",
    }
    findings = check_href_resolution_and_orphans("0000", files)
    assert [f.rule_id for f in findings] == ["M06"]
    assert findings[0].severity == Severity.WARNING


def test_href_resolution_does_not_flag_util_files_as_orphans():
    files = {
        "0000/index.xml": _index_xml(),
        "0000/util/dtd/ich-ectd-3-2.dtd": b"<!-- dtd -->",
    }
    assert check_href_resolution_and_orphans("0000", files) == []


# ---- check_lifecycle_integrity ----------------------------------------------


def test_lifecycle_integrity_catches_a_missing_prior_sequence():
    leaf = _leaf_xml(
        leaf_id_for("3.2.P.1", "0001"),
        "m3/x.pdf",
        "a" * 32,
        operation="replace",
        modified_file=f"../0000/m3/x.pdf#{leaf_id_for('3.2.P.1', '0000')}",
    )
    files = {"0001/index.xml": _index_xml(leaf), "0001/m3/x.pdf": b"data"}
    findings = check_lifecycle_integrity("0001", files, prior_files={})
    assert [f.rule_id for f in findings] == ["M08"]


def test_lifecycle_integrity_catches_a_modified_file_pointing_at_no_real_leaf():
    leaf = _leaf_xml(
        leaf_id_for("3.2.P.1", "0001"),
        "m3/x.pdf",
        "a" * 32,
        operation="replace",
        modified_file="../0000/m3/x.pdf#ID-does-not-exist",
    )
    files = {"0001/index.xml": _index_xml(leaf), "0001/m3/x.pdf": b"data"}
    prior_files = {"0000": {"0000/index.xml": _index_xml(), "0000/m3/x.pdf": b"data"}}
    findings = check_lifecycle_integrity("0001", files, prior_files)
    assert [f.rule_id for f in findings] == ["M09"]


def test_lifecycle_integrity_passes_a_real_replace_chain():
    prior_leaf = _leaf_xml(leaf_id_for("3.2.P.1", "0000"), "m3/x.pdf", md5_hex(b"old"))
    new_leaf = _leaf_xml(
        leaf_id_for("3.2.P.1", "0001"),
        "m3/x.pdf",
        md5_hex(b"new"),
        operation="replace",
        modified_file=f"../0000/m3/x.pdf#{leaf_id_for('3.2.P.1', '0000')}",
    )
    prior_files = {"0000": {"0000/index.xml": _index_xml(prior_leaf), "0000/m3/x.pdf": b"old"}}
    files = {"0001/index.xml": _index_xml(new_leaf), "0001/m3/x.pdf": b"new"}
    assert check_lifecycle_integrity("0001", files, prior_files) == []


# ---- check_pdf_specs ---------------------------------------------------------


def test_pdf_specs_catches_encryption():
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)

    findings = check_pdf_specs("0000", {"0000/m1/eu/10-cover/1.0.pdf": buffer.getvalue()})
    assert [f.rule_id for f in findings] == ["M10"]
    assert findings[0].severity == Severity.ERROR


def test_pdf_specs_warns_on_no_extractable_text():
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)  # blank -> no text
    buffer = io.BytesIO()
    writer.write(buffer)

    findings = check_pdf_specs("0000", {"0000/m1/eu/10-cover/1.0.pdf": buffer.getvalue()})
    assert [f.rule_id for f in findings] == ["M11"]
    assert findings[0].severity == Severity.WARNING


# ---- check_required_ctd_sections_present ------------------------------------


def test_required_sections_catches_a_section_that_never_appeared():
    from app.templating.registry import SECTIONS

    live = set(SECTIONS) - {"3.2.P.8.1"}
    findings = check_required_ctd_sections_present(live)
    assert [f.rule_id for f in findings] == ["M12"]
    assert findings[0].section == "3.2.P.8.1"


def test_required_sections_passes_when_everything_registered_is_live():
    from app.templating.registry import SECTIONS

    assert check_required_ctd_sections_present(set(SECTIONS)) == []


# ---- NullExternalValidator ---------------------------------------------------


def test_null_external_validator_is_advisory_only():
    findings = NullExternalValidator().validate(b"irrelevant zip bytes")
    assert len(findings) == 1
    assert findings[0].severity == Severity.ADVISORY
    assert findings[0].source == "external-validator"
