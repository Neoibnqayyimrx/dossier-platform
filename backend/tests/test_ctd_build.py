"""Tests for the P08 CTD package builder: the folder map, the NAFDAC region
profile, and the `build_ctd_package` orchestrator (placement, TOC, manifest,
determinism, and the inherited P07 validation gate).

Uses the same throwaway async SQLite engine pattern as test_assemble.py --
no real pgvector needed, since building a CTD package never touches P03's
search().
"""

from __future__ import annotations

import io
import zipfile

import pytest
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.assembly.assemble import AssemblyBlockedError
from app.core.storage import InMemoryStorageClient
from app.seed.documents import attach_certificate_documents
from app.ctd.build import build_ctd_package
from app.ctd.region_profiles import get_region_profile
from app.ctd.structure import folder_for_section
from app.models import Base, Region
from app.seed.ampiclox import build_ampiclox
from app.seed.examox import build_examox
from app.validation.engine import run_all

EXPECTED_PATHS = {
    "m1/10-cover-letter/1.0.pdf",
    "m1/12-administrative-information/1.2.pdf",
    "m2/23-quality-overall-summary/2.3.pdf",
    "m3/32-body-data/32p/32p1-description-and-composition/3.2.P.1.pdf",
    "m3/32-body-data/32p/32p8-stability/32p81-stability-summary-and-conclusion/3.2.P.8.1.pdf",
    "toc.pdf",
    "manifest.json",
}


@pytest.fixture
async def db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


# ---- structure.py / region_profiles.py (pure, no DB) ------------------------


def test_folder_for_section_rejects_unmapped_number():
    with pytest.raises(KeyError):
        folder_for_section("9.9.9")


def test_get_region_profile_rejects_unconfigured_region():
    with pytest.raises(KeyError):
        get_region_profile(Region.FDA)


def test_nafdac_profile_covers_every_certificate_and_declaration_type():
    from app.models.enums import CertificateType, DeclarationType

    profile = get_region_profile(Region.NAFDAC)
    cert_types = {t for slot in profile.module1_slots for t in slot.certificate_types}
    decl_types = {t for slot in profile.module1_slots for t in slot.declaration_types}
    assert cert_types == set(CertificateType)
    assert decl_types == set(DeclarationType)


# ---- build_ctd_package -------------------------------------------------------


async def test_package_places_every_document_in_its_correct_folder(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        result = await build_ctd_package(db, project, storage=storage)

        paths = {f.path for f in result.manifest}
        # certificates/declarations have generated UUID-suffixed filenames,
        # so check by folder membership rather than exact path.
        assert paths >= (EXPECTED_PATHS - {"manifest.json"})
        # P18: the CPP arrives as an attached document filed at its own leaf
        # (1.2.7), not as a `cpp-<uuid>` placeholder -- attach_certificate_
        # documents above is what a finished filing has done. Both appearing
        # would be the bug: a page reading "PLACEHOLDER — REPLACE THIS FILE"
        # filed next to the certificate it was standing in for.
        assert "m1/14-certificates/1.2.7.pdf" in paths
        assert not any(p.startswith("m1/14-certificates/cpp-") for p in paths)
        assert any(p.startswith("m1/15-declarations/power-of-attorney-") for p in paths)
        assert any(p.startswith("m1/15-declarations/declaration-of-authenticity-") for p in paths)

        zip_bytes = storage.get(result.storage_key)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert zf.testzip() is None
            assert "manifest.json" in zf.namelist()
            assert "toc.pdf" in zf.namelist()


async def test_manifest_md5s_match_the_actual_zipped_bytes(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        result = await build_ctd_package(db, project, storage=storage)

        zip_bytes = storage.get(result.storage_key)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            import hashlib

            for entry in result.manifest:
                actual = hashlib.md5(zf.read(entry.path)).hexdigest()
                assert actual == entry.md5


async def test_toc_lists_every_placed_document(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        result = await build_ctd_package(db, project, storage=storage)
        zip_bytes = storage.get(result.storage_key)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            # EVERY page, not just the first. P17 added fourteen
            # not-applicable statement leaves, which pushed the table onto a
            # second page -- and a one-page read then reported the last
            # entries as missing from a TOC that listed them correctly. The
            # claim being made here is "listed in the table of contents",
            # which was never a claim about page one.
            reader = PdfReader(io.BytesIO(zf.read("toc.pdf")))
            toc_text = "".join(page.extract_text() for page in reader.pages)
        # A long path can wrap across lines within its table cell -- PDF
        # text extraction then reports it with embedded line breaks. No
        # extra characters are introduced by wrapping, so stripping
        # newlines reconstructs the original contiguous path text.
        toc_text_unwrapped = toc_text.replace("\n", "")

        # toc.pdf lists every OTHER placed document, but the TOC's own
        # table is built before toc.pdf itself is added to the file set --
        # it doesn't (and can't usefully) list itself. manifest.json is
        # metadata about the package, not a submission document, so it's
        # not part of the human-facing TOC either.
        for entry in result.manifest:
            if entry.path in ("manifest.json", "toc.pdf"):
                continue
            assert entry.path in toc_text_unwrapped


async def test_rebuilding_the_same_project_is_byte_identical(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        first = await build_ctd_package(db, project, storage=storage)
        second = await build_ctd_package(db, project, storage=storage)

        assert storage.get(first.storage_key) == storage.get(second.storage_key)


async def test_build_is_blocked_by_unresolved_validation_errors(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=True)
        db.add(project)
        await db.commit()

        with pytest.raises(AssemblyBlockedError):
            await build_ctd_package(db, project, storage=InMemoryStorageClient())


async def test_build_proceeds_when_all_errors_are_overridden(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=True)
        db.add(project)
        await db.commit()

        error_ids = frozenset(f.rule_id for f in run_all(project).errors())
        assert error_ids  # sanity: there really are errors to override

        result = await build_ctd_package(
            db, project, overridden_rule_ids=error_ids, storage=InMemoryStorageClient()
        )
        assert result.manifest


async def test_a_combination_product_builds_end_to_end(db_factory):
    """AMPICLOX -- ampicillin + cloxacillin -- through the whole P07/P08
    pipeline: render, DOCX->PDF, placement, TOC, manifest, zip.

    WHY this test exists: the FDC fixture had only ever been run through
    the rule engine (P06) and the template engine (P04). No combination
    product had ever been assembled or packaged, so "the pipeline handles
    more than one active" was an assumption, not a tested fact -- and the
    one place that assumption was already false (the 2.3 QOS structure
    slot rendering apis[0] only) went unnoticed until P11c.
    """
    async with db_factory() as db:
        project = build_ampiclox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)

        # the corrected fixture is genuinely clean -- no overrides needed,
        # so this exercises the real gate rather than bypassing it.
        #
        # The attach has to happen BEFORE this line, not after: since P18 a
        # filing with its certificates still on placeholders is not clean
        # (R20), so asserting cleanliness first would be asserting it of a
        # half-built fixture.
        assert not run_all(project).errors()

        result = await build_ctd_package(db, project, storage=storage)

        paths = {f.path for f in result.manifest}
        assert paths >= (EXPECTED_PATHS - {"manifest.json"})

        with zipfile.ZipFile(io.BytesIO(storage.get(result.storage_key))) as zf:
            assert zf.testzip() is None
            qos = PdfReader(io.BytesIO(zf.read("m2/23-quality-overall-summary/2.3.pdf")))
            text = "\n".join(page.extract_text() for page in qos.pages)

        # both actives reach the assessor's page, each named -- the whole
        # point of the fix this test was written alongside.
        assert "Ampicillin" in text
        assert "Cloxacillin" in text
        assert "Structure not available" not in text
