"""Tests for app.assembly.assemble: the P07 orchestrator that renders
every registered section, converts each to a leaf PDF, and gates the
whole run on P06's validation report.

Uses a throwaway async SQLite engine (StaticPool, matching conftest.py's
own session_factory pattern) rather than the shared pg_session_factory --
assembly never calls P03's search() (no narrative is generated here, only
whatever's already approved), so it doesn't need real pgvector.
"""

from __future__ import annotations

import io

import pytest
from docx import Document
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ctd.naming import leaf_filename
from app.assembly.assemble import AssemblyBlockedError, assemble_project
from app.core.storage import InMemoryStorageClient
from app.seed.documents import attach_certificate_documents
from app.models import Base
from app.seed.examox import build_examox
from app.templating.instances import expand_sections
from app.validation.engine import run_all


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


async def test_assembling_a_clean_project_covers_every_registered_section(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        manifest = await assemble_project(db, project, storage=storage)

        # Every INSTANCE, not every registry number: a section that repeats
        # per drug substance owes one leaf per active, and its bare number
        # is never itself a leaf key.
        #
        # A SUPERSET, not an equality, since P18: the manifest also carries
        # leaves that have no registry entry at all -- an uploaded CPP or BE
        # study report is a leaf the platform places and checksums but could
        # never render. The registered sections must all still be there,
        # which is what this asserts; the extras are asserted below.
        sections = {entry.section for entry in manifest}
        assert sections >= {i.key for i in expand_sections(project)}
        assert "1.2.7" in sections  # the attached CPP, rendered by nobody
        instances = {i.key: i for i in expand_sections(project)}
        for entry in manifest:
            # gap Phase 5a: named in ICH characters after the section number
            # (plus the spec's leaf suffix), the subject carried by the folder.
            instance = instances.get(entry.section)
            suffix = instance.spec.leaf_suffix if instance is not None else None
            assert entry.filename == leaf_filename(entry.section_number, suffix)
            assert storage.get(entry.storage_path)  # actually stored, not just claimed


async def test_each_leaf_is_searchable_and_bookmarked(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        manifest = await assemble_project(db, project, storage=storage)

        # RENDERED leaves only, and the exclusion is a design decision worth
        # stating (P18): an uploaded PDF ships byte-for-byte as supplied. It
        # is not re-bookmarked, because its MD5 was computed over those exact
        # bytes at upload time and is already published in the manifest and
        # the eCTD backbone -- adding an outline entry would silently make
        # every checksum wrong. The trade-off (uploaded leaves carry whatever
        # bookmarks their author gave them) is recorded in the build log.
        rendered = {i.key for i in expand_sections(project)}
        for entry in manifest:
            if entry.section not in rendered:
                continue
            pdf_bytes = storage.get(entry.storage_path)
            reader = PdfReader(io.BytesIO(pdf_bytes))
            assert reader.pages[0].extract_text().strip()  # real text, not rasterized
            titles = [item["/Title"] for item in reader.outline]
            assert titles == [entry.title]


async def test_reassembly_is_byte_identical(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        first = await assemble_project(db, project, storage=storage)
        second = await assemble_project(db, project, storage=storage)

        first_by_section = {e.section: e for e in first}
        second_by_section = {e.section: e for e in second}
        for section, entry in first_by_section.items():
            assert entry.md5 == second_by_section[section].md5
            assert storage.get(entry.storage_path) == storage.get(
                second_by_section[section].storage_path
            )


async def test_no_mega_pdf_is_ever_produced(db_factory):
    """Granularity: one leaf per registered section, never a merged
    module PDF -- checked by confirming each stored PDF has exactly one
    section's worth of content, not several concatenated together."""
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        manifest = await assemble_project(db, project, storage=storage)

        # One leaf per registered section, PLUS one per attached document --
        # never fewer (a merge would show up as a shortfall here), and never
        # a leaf that is neither.
        rendered = {i.key for i in expand_sections(project)}
        uploaded = {d.instance_key for d in project.documents}
        assert {e.section for e in manifest} == rendered | uploaded
        assert len(manifest) == len(rendered | uploaded)

        for entry in manifest:
            if entry.section not in rendered:
                continue  # an uploaded PDF's page count is its author's business
            pdf_bytes = storage.get(entry.storage_path)
            reader = PdfReader(io.BytesIO(pdf_bytes))
            # A smoke bound, NOT the guarantee. The real granularity check is
            # the one-leaf-per-section assertion above; this catches a merged
            # module PDF, which would run to dozens of pages.
            #
            # It used to assert exactly one page, on the premise that "each
            # leaf's own docx source is a single short section". P20 outgrew
            # that premise rather than breaking it: 3.2.S.4.4 renders one row
            # per test per batch, so its length is a function of the DATA, not
            # of how many sections were concatenated. Tightening the number
            # back down would just make the test fail again the first time a
            # fixture gains a fourth batch -- which is a test measuring the
            # wrong thing, not a granularity regression.
            assert len(reader.pages) <= 12


async def test_assembly_is_blocked_by_unresolved_validation_errors(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=True)  # R01/R02/R03 errors
        db.add(project)
        await db.commit()

        with pytest.raises(AssemblyBlockedError, match="unresolved validation errors"):
            await assemble_project(db, project, storage=InMemoryStorageClient())


async def test_assembly_proceeds_when_all_errors_are_overridden(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=True)
        db.add(project)
        await db.commit()

        error_ids = frozenset(f.rule_id for f in run_all(project).errors())
        assert error_ids  # sanity: there really are errors to override

        manifest = await assemble_project(
            db, project, overridden_rule_ids=error_ids, storage=InMemoryStorageClient()
        )
        assert len(manifest) == len(expand_sections(project))


async def test_rendered_docx_source_is_not_the_pdf_itself(db_factory):
    """Sanity: the leaf PDFs are real conversions of the P04 docx output,
    not the docx bytes mislabeled -- confirms the two formats aren't
    accidentally being conflated somewhere in the pipeline."""
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        manifest = await assemble_project(db, project, storage=storage)
        p1 = next(e for e in manifest if e.section == "3.2.P.1")
        pdf_bytes = storage.get(p1.storage_path)
        assert pdf_bytes[:5] == b"%PDF-"
        with pytest.raises(Exception):
            Document(io.BytesIO(pdf_bytes))  # not a valid docx
