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
    check_fda_codes,
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
        modified_file=f"../0000/index.xml#{leaf_id_for('3.2.P.1', '0000')}",
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
        modified_file="../0000/index.xml#ID-does-not-exist",
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
        modified_file=f"../0000/index.xml#{leaf_id_for('3.2.P.1', '0000')}",
    )
    prior_files = {"0000": {"0000/index.xml": _index_xml(prior_leaf), "0000/m3/x.pdf": b"old"}}
    files = {"0001/index.xml": _index_xml(new_leaf), "0001/m3/x.pdf": b"new"}
    assert check_lifecycle_integrity("0001", files, prior_files) == []


def _regional_xml(*leaves_xml: str) -> bytes:
    """Just enough of an eu-regional.xml for the path checks, which read
    leaves, not structure (M02 is the check that reads structure)."""
    return (
        f'<eu:eu-backbone xmlns:eu="http://europa.eu.int"><m1-eu><m1-0-cover>'
        f'<specific country="common">{"".join(leaves_xml)}</specific>'
        f"</m1-0-cover></m1-eu></eu:eu-backbone>"
    ).encode()


def _index_listing_regional(sequence: str, regional: bytes) -> bytes:
    """An index.xml whose only leaf is the regional backbone -- the shape
    every built sequence has had since gap Phase 4a."""
    leaf = _leaf_xml(
        leaf_id_for("regional-backbone", sequence), "m1/eu/eu-regional.xml", md5_hex(regional)
    )
    return (
        f'<ectd:ectd xmlns:ectd="http://www.ich.org/ectd" dtd-version="3.2">'
        f"<m1-administrative-information-and-prescribing-information>{leaf}"
        f"</m1-administrative-information-and-prescribing-information></ectd:ectd>"
    ).encode()


def test_lifecycle_integrity_rejects_the_pre_4a_document_path_form():
    """Before gap Phase 4a, modified-file named the earlier PDF. ICH v3.2.2
    says it "points to the index.xml file and the leaf ID"; the old form is
    now reported as what it is, rather than accepted because it was ours."""
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
    findings = check_lifecycle_integrity("0001", files, prior_files)
    assert [f.rule_id for f in findings] == ["M07"]


def test_lifecycle_integrity_passes_a_regional_replace_chain():
    """A Module 1 leaf lives in the regional backbone, two folders down, so
    both its href and its modified-file are written from m1/eu/."""
    old_id = leaf_id_for("1.0", "0000")
    prior = {
        "0000/m1/eu/eu-regional.xml": _regional_xml(
            _leaf_xml(old_id, "10-cover/1.0.pdf", md5_hex(b"old"))
        ),
        "0000/m1/eu/10-cover/1.0.pdf": b"old",
    }
    regional = _regional_xml(
        _leaf_xml(
            leaf_id_for("1.0", "0001"),
            "10-cover/1.0.pdf",
            md5_hex(b"new"),
            operation="replace",
            modified_file=f"../../../0000/m1/eu/eu-regional.xml#{old_id}",
        )
    )
    files = {
        # index.xml lists the regional file, as every built sequence's does
        # since gap Phase 4a -- without it M06 would (rightly) call it an orphan.
        "0001/index.xml": _index_listing_regional("0001", regional),
        "0001/m1/eu/eu-regional.xml": regional,
        "0001/m1/eu/10-cover/1.0.pdf": b"new",
    }
    assert check_lifecycle_integrity("0001", files, {"0000": prior}) == []
    assert check_href_resolution_and_orphans("0001", files) == []
    assert check_checksum_integrity("0001", files) == []


def test_lifecycle_integrity_catches_a_leaf_modifying_a_different_backbone():
    """The earlier leaf exists -- but in index.xml, and this leaf is in the
    regional file. ICH has a replacement submitted "in the same location in
    the backbone" as what it replaces."""
    old_id = leaf_id_for("1.0", "0000")
    prior = {"0000/index.xml": _index_xml(_leaf_xml(old_id, "m3/x.pdf", md5_hex(b"x")))}
    files = {
        "0001/m1/eu/eu-regional.xml": _regional_xml(
            _leaf_xml(
                leaf_id_for("1.0", "0001"),
                "10-cover/1.0.pdf",
                md5_hex(b"new"),
                operation="replace",
                modified_file=f"../../../0000/index.xml#{old_id}",
            )
        ),
        "0001/m1/eu/10-cover/1.0.pdf": b"new",
    }
    findings = check_lifecycle_integrity("0001", files, {"0000": prior})
    assert [f.rule_id for f in findings] == ["M09"]


def test_a_regional_href_is_read_from_the_regional_folder_not_the_sequence_root():
    """The same href string, read the old way (from the sequence root),
    names a file that is not there."""
    regional = _regional_xml(
        _leaf_xml(leaf_id_for("1.0", "0000"), "m1/eu/10-cover/1.0.pdf", md5_hex(b"x"))
    )
    files = {
        "0000/index.xml": _index_listing_regional("0000", regional),
        "0000/m1/eu/eu-regional.xml": regional,
        "0000/m1/eu/10-cover/1.0.pdf": b"x",
    }
    rule_ids = [f.rule_id for f in check_href_resolution_and_orphans("0000", files)]
    # Resolved from m1/eu/ that is m1/eu/m1/eu/10-cover/1.0.pdf: dangling,
    # and the real file is left unreferenced.
    assert sorted(rule_ids) == ["M05", "M06"]


def test_a_delete_leaf_carries_no_file_and_is_not_a_dangling_reference():
    old_id = leaf_id_for("3.2.P.1", "0000")
    delete = (
        f'<leaf xmlns:xlink="{XLINK_NS}" ID="{leaf_id_for("3.2.P.1", "0001")}" '
        f'operation="delete" modified-file="../0000/index.xml#{old_id}" checksum="" '
        f'checksum-type="md5" xlink:type="simple"><title>t</title></leaf>'
    )
    files = {"0001/index.xml": _index_xml(delete)}
    prior = {"0000": {"0000/index.xml": _index_xml(_leaf_xml(old_id, "m3/x.pdf", "a" * 32))}}
    assert check_href_resolution_and_orphans("0001", files) == []
    assert check_checksum_integrity("0001", files) == []
    assert check_lifecycle_integrity("0001", files, prior) == []
    assert check_dtd_validity("0001", files) == []


def test_an_unreferenced_regional_backbone_is_an_orphan():
    """It used to be exempted by name, because nothing referenced it. Since
    gap Phase 4a index.xml does -- so a regional file index.xml does not
    list is a package defect, and says so."""
    files = {
        "0000/index.xml": _index_xml(),
        "0000/m1/eu/eu-regional.xml": _regional_xml(),
    }
    findings = check_href_resolution_and_orphans("0000", files)
    assert [f.rule_id for f in findings] == ["M06"]
    assert "eu-regional.xml" in findings[0].message


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


# ---- gap Phase 4c: FDA packages (M02 per region, M13) ------------------------


def _fda_regional_xml() -> bytes:
    """A real us-regional.xml, from the real builder -- which has already
    validated it against FDA's DTD before returning it."""
    import uuid
    from types import SimpleNamespace

    from app.ectd.us_regional import build_us_regional_xml
    from app.models import FDAApplicationType, RegistrationType

    project = SimpleNamespace(
        id=uuid.uuid4(),
        applicant=SimpleNamespace(
            company_name="Exagon Pharmaceuticals Ltd",
            duns_number="999999999",
            contact_name="Aisha Bello",
            contact_phone="+234-800-000-0000",
            contact_email="regulatory@exagon.example",
        ),
        application_number="000000",
        fda_application_type=FDAApplicationType.ANDA,
        product=SimpleNamespace(brand_name="EXAMOX", registration_type=RegistrationType.NEW),
    )
    return build_us_regional_xml(project, "0001", "0001", {})


def test_a_clean_fda_backbone_passes_m02_and_m13():
    files = {"0001/m1/us/us-regional.xml": _fda_regional_xml()}
    assert check_dtd_validity("0001", files) == []
    assert check_fda_codes("0001", files) == []


def test_m02_checks_an_fda_backbone_against_fda_s_dtd():
    """Before 4c, M02 knew only eu-regional.xml -- an FDA package's Module 1
    backbone went unchecked, and nothing said so."""
    broken = _fda_regional_xml().replace(b"</admin>", b"</admin><not-an-fda-heading/>")
    findings = check_dtd_validity("0001", {"0001/m1/us/us-regional.xml": broken})
    assert [f.rule_id for f in findings] == ["M02"]
    assert "us-regional.xml" in findings[0].message
    assert "us-regional-v3-3.dtd" in findings[0].message


def test_m13_catches_a_code_fda_s_dtd_happily_accepts():
    """The whole reason M13 exists: this document is DTD-VALID."""
    tampered = _fda_regional_xml().replace(
        b'application-type="fdaat2"', b'application-type="banana"'
    )
    files = {"0001/m1/us/us-regional.xml": tampered}
    assert check_dtd_validity("0001", files) == []
    findings = check_fda_codes("0001", files)
    assert [f.rule_id for f in findings] == ["M13"]
    assert findings[0].severity == Severity.ERROR
    assert "banana" in findings[0].message and "application-type.xml" in findings[0].message


def test_m13_rejects_a_code_fda_has_retired(monkeypatch):
    """ "Only coded values with a status of 'active' should be submitted"
    (FDA Module 1 spec v2.6). None of today's codes is inactive, so the list
    is patched to retire one -- the day FDA does it, this is the finding."""
    from app.ectd import us_regional

    real = us_regional.code_list

    def retired_sub_types(name):
        codes = dict(real(name))
        if name == "submission-sub-type":
            codes["fdasst3"] = "inactive"
        return codes

    monkeypatch.setattr(us_regional, "code_list", retired_sub_types)
    findings = check_fda_codes("0001", {"0001/m1/us/us-regional.xml": _fda_regional_xml()})
    assert [f.rule_id for f in findings] == ["M13"]
    assert "'inactive'" in findings[0].message


def test_m13_does_not_look_at_packages_that_are_not_fda():
    assert check_fda_codes("0000", {"0000/index.xml": _index_xml()}) == []
