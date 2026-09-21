"""Tests for the P09 eCTD v3.2.2 backbone: real-DTD-validated index.xml/
eu-regional.xml construction, the lifecycle resolver, and the full
`build_ectd_sequence` orchestrator across two sequences.

Uses the same throwaway async SQLite engine pattern as test_ctd_build.py --
no real pgvector needed, since building an eCTD sequence never touches
P03's search(). EXAMOX is reused with `region` overridden to EU, since
none of its planted validation content is NAFDAC-specific (R13/R14/R16 are
all `regions=[Region.NAFDAC]`-scoped and simply don't apply).
"""

from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.assembly.assemble import AssemblyBlockedError
from app.core.storage import InMemoryStorageClient
from app.seed.documents import attach_certificate_documents
from app.ectd.build import build_ectd_sequence
from app.ectd.checksum import md5_hex
from app.ectd.index_xml import build_index_xml
from app.ectd.leaf import XLINK_NS, Leaf, leaf_id_for, slugify_section_key
from app.ectd.lifecycle import NewLeafInput, resolve_lifecycle
from app.ectd.regional import build_regional_xml
from app.models import Base, Region, Sequence
from app.seed.ampiclox import build_ampiclox
from app.seed.examox import build_examox
from app.validation.engine import run_all

# ---- leaf.py (pure) --------------------------------------------------------


def test_leaf_id_is_deterministic_and_starts_with_a_letter():
    assert leaf_id_for("3.2.P.1", "0000") == leaf_id_for("3.2.P.1", "0000")
    assert leaf_id_for("3.2.P.1", "0000") != leaf_id_for("3.2.P.1", "0001")
    assert slugify_section_key("3.2.P.1")[0].isdigit()  # the raw slug does start with a digit...
    assert leaf_id_for("3.2.P.1", "0000")[0].isalpha()  # ...but the real ID never does


def test_build_leaf_element_requires_modified_file_for_non_new_operations():
    from app.ectd.leaf import build_leaf_element

    leaf = Leaf(id="x", title="t", href="h", checksum="a" * 32, operation="replace")
    with pytest.raises(ValueError):
        build_leaf_element(leaf)


def test_sequence_number_of_inverts_leaf_id_for():
    from app.ectd.leaf import sequence_number_of

    assert sequence_number_of(leaf_id_for("3.2.P.1", "0007")) == "0007"
    assert sequence_number_of(leaf_id_for("certificate:1234-abcd", "0000")) == "0000"
    with pytest.raises(ValueError):
        sequence_number_of("a1234567")  # somebody else's ID scheme


def test_a_leaf_in_index_xml_points_at_the_earlier_index_xml():
    """ICH v3.2.2 Appendix 6, verbatim example: modified-file="../0001/index.xml#a1234567"."""
    from app.ectd.leaf import build_leaf_element

    el = build_leaf_element(
        Leaf(
            id=leaf_id_for("3.2.P.1", "0002"),
            title="t",
            href="m3/32-body-data/3.2.P.1.pdf",
            checksum="a" * 32,
            operation="replace",
            modifies=leaf_id_for("3.2.P.1", "0001"),
        )
    )
    assert el.get("modified-file") == "../0001/index.xml#ID-3-2-P-1-0001"
    assert el.get(f"{{{XLINK_NS}}}href") == "m3/32-body-data/3.2.P.1.pdf"


def test_a_leaf_in_a_regional_backbone_is_written_from_that_file_s_folder():
    """FDA's Module 1 spec v2.6, section V: "the xlink:href and modified-file
    leaf attributes should reflect the path relative to the location of the
    us-regional.xml file", with the example
    modified-file="../../../0001/m1/us/us-regional.xml#id34567"."""
    from app.ectd.leaf import build_leaf_element

    el = build_leaf_element(
        Leaf(
            id=leaf_id_for("1.0", "0002"),
            title="t",
            href="m1/eu/10-cover/1.0.pdf",
            checksum="a" * 32,
            operation="replace",
            modifies=leaf_id_for("1.0", "0001"),
        ),
        "m1/eu/eu-regional.xml",
    )
    assert el.get(f"{{{XLINK_NS}}}href") == "10-cover/1.0.pdf"
    assert el.get("modified-file") == "../../../0001/m1/eu/eu-regional.xml#ID-1-0-0001"


def test_a_delete_leaf_has_no_href_and_an_empty_checksum():
    from app.ectd.leaf import build_leaf_element

    el = build_leaf_element(
        Leaf(
            id=leaf_id_for("3.2.P.1", "0001"),
            title="t",
            href=None,
            checksum="",
            operation="delete",
            modifies=leaf_id_for("3.2.P.1", "0000"),
        )
    )
    assert el.get(f"{{{XLINK_NS}}}href") is None
    assert el.get("checksum") == ""


def test_only_a_delete_may_have_no_file():
    from app.ectd.leaf import build_leaf_element

    with pytest.raises(ValueError, match="only a delete"):
        build_leaf_element(Leaf(id="x", title="t", href=None, checksum="", operation="new"))


# ---- index_xml.py / regional.py (pure, DTD-validated) ----------------------


def _sample_leaves() -> dict[str, Leaf]:
    return {
        "2.3": Leaf(
            id=leaf_id_for("2.3", "0000"),
            title="QOS",
            href="m2/23-quality-overall-summary/2.3.pdf",
            checksum="a" * 32,
            operation="new",
        ),
        "3.2.P.1": Leaf(
            id=leaf_id_for("3.2.P.1", "0000"),
            title="Description and Composition",
            href="m3/32-body-data/32p/32p1-description-and-composition/3.2.P.1.pdf",
            checksum="b" * 32,
            operation="new",
        ),
        "3.2.P.8.1": Leaf(
            id=leaf_id_for("3.2.P.8.1", "0000"),
            title="Stability Summary",
            href="m3/32-body-data/32p/32p8-stability/32p81-stability-summary-and-conclusion/3.2.P.8.1.pdf",
            checksum="c" * 32,
            operation="new",
        ),
    }


def test_build_index_xml_is_dtd_valid_and_byte_stable():
    leaves = _sample_leaves()
    first = build_index_xml(leaves)
    second = build_index_xml(leaves)
    assert first == second
    assert b"m3-2-p-1-description-and-composition-of-the-drug-product" in first


def test_build_index_xml_skips_module1_only_keys():
    leaves = _sample_leaves()
    leaves["1.0"] = Leaf(
        id=leaf_id_for("1.0", "0000"),
        title="Cover",
        href="m1/eu/10-cover/1.0.pdf",
        checksum="d" * 32,
        operation="new",
    )
    xml_bytes = build_index_xml(leaves)
    # 1.0 has no ICH_HEADING_PATH entry -- it must never appear in index.xml.
    assert leaf_id_for("1.0", "0000").encode() not in xml_bytes


def test_index_xml_attach_rejects_a_child_with_no_declared_dtd_order():
    # White-box: `_attach` is the one place that would otherwise silently
    # emit children in whatever order they happened to be inserted --
    # exercise its guard directly rather than trying to smuggle a fake
    # heading through the real ICH_HEADING_PATH registry.
    from app.ectd.index_xml import _Node, _attach
    from lxml import etree

    node = _Node("m3-quality")
    node.child("not-a-real-ich-heading")

    with pytest.raises(ValueError, match="no declared DTD order"):
        _attach(etree.Element("m3-quality"), node)


def test_build_regional_xml_is_dtd_valid_and_always_includes_mandatory_cover():
    import uuid
    from types import SimpleNamespace

    from app.models.enums import RegistrationType

    project = SimpleNamespace(
        id=uuid.uuid4(),
        applicant=SimpleNamespace(company_name="Exagon Pharmaceuticals Ltd"),
        product=SimpleNamespace(
            brand_name="EXAMOX",
            registration_type=RegistrationType.NEW,
            apis=[SimpleNamespace(inn_name="Amoxicillin")],
        ),
    )
    # No cover-letter leaf this round (e.g. an unchanged-cover-letter
    # sequence) -- must still validate, per m1-0-cover being mandatory.
    xml_bytes = build_regional_xml(project, "0001", ["0000"], {"registration-form": []})
    assert b"<m1-0-cover>" in xml_bytes
    assert b"<related-sequence>0000</related-sequence>" in xml_bytes


# ---- lifecycle.py (pure) ---------------------------------------------------


def test_lifecycle_first_sequence_is_all_new():
    result = resolve_lifecycle(
        [], [NewLeafInput("3.2.P.1", "Description", "m3/.../3.2.P.1.pdf", "a" * 32)], "0000"
    )
    assert result.backbone_leaves["3.2.P.1"].operation == "new"
    assert "3.2.P.1" in result.cumulative_leaves


def test_lifecycle_omits_unchanged_leaves_but_carries_them_forward():
    seq0 = resolve_lifecycle(
        [],
        [
            NewLeafInput("3.2.P.1", "Description", "m3/.../3.2.P.1.pdf", "a" * 32),
            NewLeafInput("3.2.P.8.1", "Stability", "m3/.../3.2.P.8.1.pdf", "b" * 32),
        ],
        "0000",
    )
    seq1 = resolve_lifecycle(
        list(seq0.cumulative_leaves.values()),
        [
            NewLeafInput("3.2.P.1", "Description", "m3/.../3.2.P.1.pdf", "c" * 32),  # changed
            NewLeafInput("3.2.P.8.1", "Stability", "m3/.../3.2.P.8.1.pdf", "b" * 32),  # unchanged
        ],
        "0001",
    )
    assert set(seq1.backbone_leaves) == {"3.2.P.1"}
    assert seq1.backbone_leaves["3.2.P.1"].operation == "replace"
    assert seq1.backbone_leaves["3.2.P.1"].modifies == seq0.cumulative_leaves["3.2.P.1"].leaf_id
    # the unchanged leaf is still tracked in the cumulative view for the
    # NEXT sequence's diff, just absent from this sequence's own backbone.
    assert set(seq1.cumulative_leaves) == {"3.2.P.1", "3.2.P.8.1"}


def test_lifecycle_deletes_by_naming_the_retired_leaf_and_carrying_no_file():
    seq0 = resolve_lifecycle(
        [], [NewLeafInput("3.2.P.8.1", "Stability", "m3/.../3.2.P.8.1.pdf", "a" * 32)], "0000"
    )
    seq1 = resolve_lifecycle(list(seq0.cumulative_leaves.values()), [], "0001")
    deleted = seq1.backbone_leaves["3.2.P.8.1"]
    assert deleted.operation == "delete"
    assert deleted.modifies == leaf_id_for("3.2.P.8.1", "0000")
    # ICH v3.2.2 Appendix 6: a delete submits no file, and its checksum
    # "will be empty". Restating the old href pointed at a path inside THIS
    # sequence where nothing exists.
    assert deleted.href is None
    assert deleted.checksum == ""
    assert "3.2.P.8.1" not in seq1.cumulative_leaves


def test_lifecycle_targets_the_sequence_that_last_changed_the_document():
    """Regression, found in gap Phase 4a: the resolver built modified-file
    from "the immediately prior sequence". Right only when the document
    changed in that very sequence. Here B is untouched in 0001, so its live
    leaf is still 0000's -- and the replace in 0002 used to point at 0001,
    whose backbone never mentioned B."""
    seq0 = resolve_lifecycle(
        [],
        [
            NewLeafInput("A", "A", "m3/a.pdf", "a" * 32),
            NewLeafInput("B", "B", "m3/b.pdf", "b" * 32),
        ],
        "0000",
    )
    seq1 = resolve_lifecycle(
        list(seq0.cumulative_leaves.values()),
        [
            NewLeafInput("A", "A", "m3/a.pdf", "c" * 32),  # changed
            NewLeafInput("B", "B", "m3/b.pdf", "b" * 32),  # untouched
        ],
        "0001",
    )
    assert "B" not in seq1.backbone_leaves
    seq2 = resolve_lifecycle(
        list(seq1.cumulative_leaves.values()),
        [
            NewLeafInput("A", "A", "m3/a.pdf", "c" * 32),
            NewLeafInput("B", "B", "m3/b.pdf", "d" * 32),  # changed at last
        ],
        "0002",
    )
    assert seq2.backbone_leaves["B"].modifies == leaf_id_for("B", "0000")


# ---- checksum.py: tamper detection -----------------------------------------


def test_tampering_with_leaf_bytes_changes_its_checksum():
    original = b"%PDF-1.4 fake pdf content"
    tampered = original + b"\x00"
    assert md5_hex(original) != md5_hex(tampered)


# ---- build_ectd_sequence (integration) -------------------------------------


@pytest.fixture
async def db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _eu_examox(buggy: bool = False):
    project = build_examox(buggy=buggy)
    project.region = Region.EU
    return project


async def test_first_sequence_is_dtd_valid_and_places_every_document(db_factory):
    async with db_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()

        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        result = await build_ectd_sequence(db, project, seq0, storage=storage)

        assert set(result.operations.values()) == {"new"}
        zip_bytes = storage.get(result.storage_key)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert zf.testzip() is None
            names = zf.namelist()
            assert "0000/index.xml" in names
            assert "0000/index-md5.txt" in names
            assert "0000/m1/eu/eu-regional.xml" in names
            assert "0000/util/dtd/ich-ectd-3-2.dtd" in names
            assert "0000/m3/32-body-data/32p/32p1-description-and-composition/3.2.P.1.pdf" in names
            # index-md5.txt really is the MD5 of the index.xml bytes it ships alongside.
            index_md5 = zf.read("0000/index-md5.txt").decode()
            assert md5_hex(zf.read("0000/index.xml")) in index_md5


async def test_rebuilding_the_same_sequence_is_byte_identical(db_factory):
    async with db_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        storage = InMemoryStorageClient()
        first = await build_ectd_sequence(db, project, seq0, storage=storage)
        second = await build_ectd_sequence(db, project, seq0, storage=storage)
        assert storage.get(first.storage_key) == storage.get(second.storage_key)


async def test_second_sequence_only_replaces_the_changed_leaf(db_factory):
    async with db_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()
        await build_ectd_sequence(db, project, seq0, storage=storage)

        certificate = project.product.certificates[0]
        certificate.certificate_number = "CPP-CHANGED-999"

        seq1 = Sequence(project_id=project.id, number="0001")
        db.add(seq1)
        await db.commit()
        result = await build_ectd_sequence(db, project, seq1, storage=storage)

        assert list(result.operations.values()) == ["replace"]
        (changed_key,) = result.operations.keys()
        assert changed_key.startswith("certificate:")

        zip_bytes = storage.get(result.storage_key)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            # Only the changed certificate's physical file ships in 0001 --
            # every unchanged section's PDF is NOT duplicated here.
            pdfs = [n for n in names if n.endswith(".pdf")]
            assert len(pdfs) == 1
            assert "certificates/cpp-" in pdfs[0]
            regional_xml = zf.read("0001/m1/eu/eu-regional.xml")
            assert b'operation="replace"' in regional_xml
            # Relative to m1/eu/, pointing at the earlier REGIONAL backbone
            # (where the certificate's leaf lives), not at its PDF.
            assert b'modified-file="../../../0000/m1/eu/eu-regional.xml#ID-certificate-' in (
                regional_xml
            )


def _unzip(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


async def test_index_xml_lists_and_checksums_the_regional_backbone(db_factory):
    """ICH v3.2.2 Appendix 6: the regional file's leaf in index.xml is
    "always 'new'", and it is how that file gets a checksum at all."""
    import posixpath

    from app.ectd.validate import run_mechanical_checks

    async with db_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        storage = InMemoryStorageClient()
        result = await build_ectd_sequence(db, project, seq0, storage=storage)
        files = _unzip(storage.get(result.storage_key))

    index = etree.fromstring(files["0000/index.xml"])
    (m1_leaf,) = index.findall("m1-administrative-information-and-prescribing-information/leaf")
    assert m1_leaf.get(f"{{{XLINK_NS}}}href") == "m1/eu/eu-regional.xml"
    assert m1_leaf.get("operation") == "new"
    assert m1_leaf.get("checksum") == md5_hex(files["0000/m1/eu/eu-regional.xml"])

    # Every regional href resolves from m1/eu/, and none is written from
    # the sequence root any more.
    regional = etree.fromstring(files["0000/m1/eu/eu-regional.xml"])
    hrefs = [leaf.get(f"{{{XLINK_NS}}}href") for leaf in regional.iter("leaf")]
    assert hrefs and not any(h.startswith("m1/") for h in hrefs)
    assert all(posixpath.normpath(f"0000/m1/eu/{h}") in files for h in hrefs)

    mechanical = run_mechanical_checks(
        "0000", files, {}, live_section_keys=set(), expected_section_keys=set()
    )
    assert [f for f in mechanical if f.rule_id in {"M01", "M02", "M03", "M04", "M05", "M06"}] == []


async def test_a_document_replaced_after_sitting_unchanged_validates_cleanly(db_factory):
    """The skipped-sequence bug, end to end, judged by the P10 validator.

    The CPP changes in 0001; the TSE/BSE certificate does not change until
    0002. Its live leaf is therefore 0000's. Before gap Phase 4a, 0002's
    replace pointed at 0001 -- whose backbone never mentioned it -- and M09
    fired on a package this project had just built.
    """
    from app.ectd.validate import check_lifecycle_integrity

    async with db_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()
        storage = InMemoryStorageClient()
        cpp, tse = project.product.certificates

        bundles: dict[str, dict[str, bytes]] = {}
        for number, change in (
            ("0000", None),
            ("0001", lambda: setattr(cpp, "certificate_number", "CPP-CHANGED")),
            ("0002", lambda: setattr(tse, "certificate_number", "TSE-CHANGED")),
        ):
            if change:
                change()
            sequence = Sequence(project_id=project.id, number=number)
            db.add(sequence)
            await db.commit()
            result = await build_ectd_sequence(db, project, sequence, storage=storage)
            bundles[number] = _unzip(storage.get(result.storage_key))

    regional = bundles["0002"]["0002/m1/eu/eu-regional.xml"]
    tse_old = f"ID-certificate-{tse.id}-0000".encode()
    assert b'modified-file="../../../0000/m1/eu/eu-regional.xml#' + tse_old in regional
    assert (
        check_lifecycle_integrity(
            "0002", bundles["0002"], {"0000": bundles["0000"], "0001": bundles["0001"]}
        )
        == []
    )


async def test_build_is_blocked_by_unresolved_validation_errors(db_factory):
    async with db_factory() as db:
        project = _eu_examox(buggy=True)
        db.add(project)
        await db.commit()
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        with pytest.raises(AssemblyBlockedError):
            await build_ectd_sequence(db, project, seq0, storage=InMemoryStorageClient())


async def test_build_proceeds_when_all_errors_are_overridden(db_factory):
    async with db_factory() as db:
        project = _eu_examox(buggy=True)
        db.add(project)
        await db.commit()
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        error_ids = frozenset(f.rule_id for f in run_all(project).errors())
        assert error_ids

        result = await build_ectd_sequence(
            db, project, seq0, overridden_rule_ids=error_ids, storage=InMemoryStorageClient()
        )
        assert result.operations


async def test_combination_product_gets_one_drug_substance_element_per_active(db_factory):
    """The ICH DTD declares `m3-2-s-drug-substance*` -- starred, repeating --
    with `substance` and `manufacturer` both #REQUIRED. AMPICLOX therefore
    owes TWO of those elements, each carrying its own substance's name and
    maker, each holding that substance's 3.2.S leaves.

    This is the test that actually exercises repetition: every other eCTD
    test uses EXAMOX, which has one active, so a backbone builder that
    silently merged all substances into a single element would pass all of
    them -- and would produce a DTD-VALID package filing cloxacillin's
    specification under ampicillin's name.
    """
    async with db_factory() as db:
        project = build_ampiclox(buggy=False)
        project.region = Region.EU
        db.add(project)
        await db.commit()
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        result = await build_ectd_sequence(db, project, seq0, storage=storage)

        with zipfile.ZipFile(io.BytesIO(storage.get(result.storage_key))) as zf:
            names = set(zf.namelist())
            index = etree.fromstring(zf.read("0000/index.xml"))

        elements = index.findall(".//m3-2-s-drug-substance")
        assert len(elements) == 2
        assert [e.get("substance") for e in elements] == ["Ampicillin", "Cloxacillin"]
        # #REQUIRED, and it must be the substance's maker -- not the
        # finished-product site the earlier seeds only had.
        assert {e.get("manufacturer") for e in elements} == {"Exagon API Division"}

        # each substance's own leaves live under its own element, not pooled
        for element, substance in zip(elements, ("ampicillin", "cloxacillin")):
            hrefs = [
                leaf.get("{http://www.w3c.org/1999/xlink}href") for leaf in element.iter("leaf")
            ]
            assert hrefs, f"no leaves filed under {substance}"
            assert all(f"32s-{substance}/" in href for href in hrefs), hrefs

        # and the physical files are where the backbone says they are
        assert (
            "0000/m3/32-body-data/32s/32s-cloxacillin/32s4-control-of-drug-substance"
            "/32s41-specification/3.2.S.4.1-cloxacillin.pdf" in names
        )


async def test_replacing_an_uploaded_document_still_drives_the_lifecycle(db_factory):
    """P26 regression: versioning must not disturb the lifecycle resolver.

    `resolve_lifecycle` decides new-vs-replace by comparing a leaf's
    checksum against the previous sequence's. P26 put a version table
    behind uploaded documents, and the thing that had to stay true is that
    the resolver still sees the CURRENT version and nothing else -- if it
    read a stale row, a replaced document would file as unchanged and the
    agency would never receive the new file.

    Built on the AMLODIPINE worked example the phase brief names -- the
    filed Me Cure dossier behind `docs/target-toc.yaml`, seeded by
    `app/seed/amlodipine.py` and already the subject of
    `tests/test_worked_example.py`. Its region is switched to EU here for
    the same reason that file switches it: EU is the only regional Module 1
    this platform models, and Modules 2-5 (where our leaf lives) are common
    to every region anyway.
    """
    from datetime import datetime, timezone

    from app.documents.ingest import ingest_document, versioned_storage_key_for
    from app.models import DocumentVersion, SectionDocument
    from app.seed.documents import MINIMAL_PDF

    leaf = "5.3.1.2"  # a CRO's BE report: Modules 2-5 are common to every region

    from app.seed.amlodipine import build_amlodipine

    async with db_factory() as db:
        project = build_amlodipine()
        project.region = Region.EU
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)

        original = MINIMAL_PDF.replace(b"%%EOF", b"% first\n%%EOF")
        first = ingest_document(
            project_id=project.id,
            instance_key=leaf,
            data=original,
            content_type="application/pdf",
            filename="BE_report_first.pdf",
            storage=storage,
            storage_key=versioned_storage_key_for(project.id, leaf, 1),
        )
        document = SectionDocument(
            project_id=project.id,
            section_number=leaf,
            subject_slug="",
            storage_key=first.storage_key,
            md5=first.md5,
            size_bytes=first.size_bytes,
            original_filename="BE_report_first.pdf",
            content_type=first.content_type,
            uploaded_at=datetime.now(timezone.utc),
        )
        document.versions.append(
            DocumentVersion(
                version_number=1,
                storage_key=first.storage_key,
                md5=first.md5,
                size_bytes=first.size_bytes,
                original_filename="BE_report_first.pdf",
                content_type=first.content_type,
                uploaded_at=datetime.now(timezone.utc),
            )
        )
        # Appended to the relationship, not merely db.add()'d: the builder
        # walks `project.documents`, and a row that exists in the table but
        # not on the loaded object is invisible to it.
        project.documents.append(document)
        await db.commit()

        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()
        await build_ectd_sequence(db, project, seq0, storage=storage)

        # A new version of the SAME leaf -- exactly what the upload route
        # does: new bytes at a new key, the document's columns advanced to
        # describe them, the old version left intact.
        replacement = MINIMAL_PDF.replace(b"%%EOF", b"% second\n%%EOF")
        second = ingest_document(
            project_id=project.id,
            instance_key=leaf,
            data=replacement,
            content_type="application/pdf",
            filename="BE_report_second.pdf",
            storage=storage,
            storage_key=versioned_storage_key_for(project.id, leaf, 2),
        )
        assert second.md5 != first.md5
        document.storage_key = second.storage_key
        document.md5 = second.md5
        document.size_bytes = second.size_bytes
        document.versions.append(
            DocumentVersion(
                version_number=2,
                storage_key=second.storage_key,
                md5=second.md5,
                size_bytes=second.size_bytes,
                original_filename="BE_report_second.pdf",
                content_type=second.content_type,
                uploaded_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        seq1 = Sequence(project_id=project.id, number="0001")
        db.add(seq1)
        await db.commit()
        result = await build_ectd_sequence(db, project, seq1, storage=storage)

        # Exactly one leaf changed, it is ours, and it is a replace.
        changed = {key: op for key, op in result.operations.items() if op != "new"}
        assert list(changed.values()) == ["replace"], result.operations
        (changed_key,) = changed.keys()
        assert leaf in changed_key, changed_key

        # The sequence ships the NEW bytes, not the superseded ones.
        zip_bytes = storage.get(result.storage_key)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            shipped = [n for n in zf.namelist() if n.endswith(".pdf")]
            assert len(shipped) == 1, shipped
            assert md5_hex(zf.read(shipped[0])) == second.md5
            # The operation lives in the ICH backbone, not the EU regional
            # one: 5.3.1.2 is a Module 5 leaf and eu-regional.xml carries
            # only Module 1.
            index_xml = zf.read("0001/index.xml")
            assert b'operation="replace"' in index_xml
            assert b'modified-file="../0000/index.xml#ID-' in index_xml

        # ...and version 1's bytes survived being replaced.
        assert storage.get(first.storage_key) == original


async def test_the_sequence_type_reaches_the_envelope_instead_of_a_hardcoded_initial(
    db_factory,
):
    """P27 regression: `submission-unit/@type` was a constant.

    `app/ectd/regional.py` set type="initial" on EVERY sequence, so a
    response to a deficiency letter was filed telling the agency it was a
    fresh submission. DTD-valid, and wrong -- which is the kind of defect
    that survives validation all the way to a reviewer.

    The values come from the EU regional DTD's own enumeration for the
    attribute, so a filer's choice is automatically a legal one; this test
    also proves the chosen value still passes DTD validation, which
    build_regional_xml performs before returning.
    """
    from app.models import SubmissionUnitType

    async with db_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)

        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()
        first = await build_ectd_sequence(db, project, seq0, storage=storage)

        with zipfile.ZipFile(io.BytesIO(storage.get(first.storage_key))) as zf:
            assert b'<submission-unit type="initial"/>' in zf.read("0000/m1/eu/eu-regional.xml")

        # The next sequence answers the agency, and says so.
        seq1 = Sequence(
            project_id=project.id,
            number="0001",
            submission_unit_type=SubmissionUnitType.RESPONSE,
        )
        db.add(seq1)
        await db.commit()
        second = await build_ectd_sequence(db, project, seq1, storage=storage)

        with zipfile.ZipFile(io.BytesIO(storage.get(second.storage_key))) as zf:
            regional = zf.read("0001/m1/eu/eu-regional.xml")
        assert b'<submission-unit type="response"/>' in regional
        assert b'type="initial"' not in regional

        # The OTHER type axis is untouched: `submission/@type` still comes
        # from the product's registration type, because "this is a renewal"
        # and "this sequence is a response" are both true at once.
        assert b'<submission type="renewal">' in regional
