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

from app.assembly.assemble import AssemblyBlockedError, assemble_project
from app.core.storage import InMemoryStorageClient
from app.models import Base
from app.seed.examox import build_examox
from app.templating.registry import SECTIONS
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
        manifest = await assemble_project(db, project, storage=storage)

        assert {entry.section for entry in manifest} == set(SECTIONS)
        for entry in manifest:
            assert entry.filename == f"{entry.section}.pdf"
            assert storage.get(entry.storage_path)  # actually stored, not just claimed


async def test_each_leaf_is_searchable_and_bookmarked(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        manifest = await assemble_project(db, project, storage=storage)

        for entry in manifest:
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
        manifest = await assemble_project(db, project, storage=storage)

        assert len(manifest) == len(SECTIONS)
        for entry in manifest:
            pdf_bytes = storage.get(entry.storage_path)
            reader = PdfReader(io.BytesIO(pdf_bytes))
            # each leaf's own docx source is a single short section, so a
            # merged multi-section PDF would visibly have far more pages.
            assert len(reader.pages) == 1


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
        assert len(manifest) == len(SECTIONS)


async def test_rendered_docx_source_is_not_the_pdf_itself(db_factory):
    """Sanity: the leaf PDFs are real conversions of the P04 docx output,
    not the docx bytes mislabeled -- confirms the two formats aren't
    accidentally being conflated somewhere in the pipeline."""
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        manifest = await assemble_project(db, project, storage=storage)
        p1 = next(e for e in manifest if e.section == "3.2.P.1")
        pdf_bytes = storage.get(p1.storage_path)
        assert pdf_bytes[:5] == b"%PDF-"
        with pytest.raises(Exception):
            Document(io.BytesIO(pdf_bytes))  # not a valid docx
