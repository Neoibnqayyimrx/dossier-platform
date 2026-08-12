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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.assembly.assemble import AssemblyBlockedError
from app.core.storage import InMemoryStorageClient
from app.ectd.build import build_ectd_sequence
from app.ectd.checksum import md5_hex
from app.ectd.index_xml import build_index_xml
from app.ectd.leaf import Leaf, leaf_id_for, slugify_section_key
from app.ectd.lifecycle import NewLeafInput, resolve_lifecycle
from app.ectd.regional import build_regional_xml
from app.models import Base, Region, Sequence
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
        id=leaf_id_for("1.0", "0000"), title="Cover", href="m1/eu/10-cover/1.0.pdf",
        checksum="d" * 32, operation="new",
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
        None, [], [NewLeafInput("3.2.P.1", "Description", "m3/.../3.2.P.1.pdf", "a" * 32)], "0000"
    )
    assert result.backbone_leaves["3.2.P.1"].operation == "new"
    assert "3.2.P.1" in result.cumulative_leaves


def test_lifecycle_omits_unchanged_leaves_but_carries_them_forward():
    seq0 = resolve_lifecycle(
        None,
        [],
        [
            NewLeafInput("3.2.P.1", "Description", "m3/.../3.2.P.1.pdf", "a" * 32),
            NewLeafInput("3.2.P.8.1", "Stability", "m3/.../3.2.P.8.1.pdf", "b" * 32),
        ],
        "0000",
    )
    seq1 = resolve_lifecycle(
        "0000",
        list(seq0.cumulative_leaves.values()),
        [
            NewLeafInput("3.2.P.1", "Description", "m3/.../3.2.P.1.pdf", "c" * 32),  # changed
            NewLeafInput("3.2.P.8.1", "Stability", "m3/.../3.2.P.8.1.pdf", "b" * 32),  # unchanged
        ],
        "0001",
    )
    assert set(seq1.backbone_leaves) == {"3.2.P.1"}
    assert seq1.backbone_leaves["3.2.P.1"].operation == "replace"
    assert seq1.backbone_leaves["3.2.P.1"].modified_file == (
        f"../0000/m3/.../3.2.P.1.pdf#{seq0.cumulative_leaves['3.2.P.1'].leaf_id}"
    )
    # the unchanged leaf is still tracked in the cumulative view for the
    # NEXT sequence's diff, just absent from this sequence's own backbone.
    assert set(seq1.cumulative_leaves) == {"3.2.P.1", "3.2.P.8.1"}


def test_lifecycle_three_sequences_deep_deletes_correctly():
    seq0 = resolve_lifecycle(
        None, [], [NewLeafInput("3.2.P.8.1", "Stability", "m3/.../3.2.P.8.1.pdf", "a" * 32)], "0000"
    )
    seq1 = resolve_lifecycle("0000", list(seq0.cumulative_leaves.values()), [], "0001")
    assert seq1.backbone_leaves["3.2.P.8.1"].operation == "delete"
    assert "3.2.P.8.1" not in seq1.cumulative_leaves


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
            assert b'modified-file="../0000/' in regional_xml


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
