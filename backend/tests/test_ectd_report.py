"""Integration tests for the P10 consolidated report (app.ectd.report).

`run_ai_review=False` keeps most tests on the throwaway SQLite engine
(matching every other P09/P10 test) -- the AI reviewer needs real pgvector
for `app.knowledge.retrieve.search`, so its one dedicated test uses
`pg_session_factory` and self-skips without a real Postgres, same
convention as P03's KB-search tests.
"""

from __future__ import annotations

import zipfile
import io

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.storage import InMemoryStorageClient
from app.ectd.build import build_ectd_sequence
from app.ectd.report import SequenceNotBuiltError, validate_ectd_sequence
from app.models import Base, NarrativeStatus, Region, Sequence
from app.models.narrative import NarrativeGeneration
from app.seed.examox import build_examox
from app.validation.engine import Severity


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


async def test_clean_sequence_passes_with_only_the_null_validator_advisory(db_factory):
    async with db_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        storage = InMemoryStorageClient()
        await build_ectd_sequence(db, project, seq0, storage=storage)

        report = await validate_ectd_sequence(
            db, project, seq0, storage=storage, run_ai_review=False
        )

        assert report.is_exportable()

        # A clean BUILD means zero mechanical findings -- proves the
        # checks don't false-positive on a real package.
        assert [f for f in report.findings if f.source == "mechanical-ectd"] == []

        # P06's own findings are still here (that's what "consolidated"
        # means) -- including R11, the pharmacopoeia-version INFO reminder
        # that deliberately fires on every clean dossier too. Their
        # presence alongside eCTD findings, each tagged with its own
        # source, is exactly the provenance this report exists to carry.
        assert any(f.source == "data-rule" for f in report.findings)

        # ...and the null validator's honest "internal checks only" note.
        external = [f for f in report.findings if f.source == "external-validator"]
        assert len(external) == 1
        assert external[0].severity == Severity.ADVISORY


async def test_validating_an_unbuilt_sequence_raises(db_factory):
    async with db_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        with pytest.raises(SequenceNotBuiltError):
            await validate_ectd_sequence(
                db, project, seq0, storage=InMemoryStorageClient(), run_ai_review=False
            )


async def test_tampering_with_the_stored_package_is_caught_and_blocks_export(db_factory):
    async with db_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        storage = InMemoryStorageClient()
        result = await build_ectd_sequence(db, project, seq0, storage=storage)

        # Simulate corruption at rest: rewrite the stored zip with one
        # leaf's bytes flipped, everything else identical.
        original = storage.get(result.storage_key)
        with zipfile.ZipFile(io.BytesIO(original)) as zf:
            names = zf.namelist()
            contents = {n: zf.read(n) for n in names}
        target = next(n for n in names if n.endswith("3.2.P.1.pdf"))
        contents[target] += b"\x00corrupted"

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            for name, data in contents.items():
                zf.writestr(name, data)
        storage.put(result.storage_key, buffer.getvalue(), "application/zip")

        report = await validate_ectd_sequence(
            db, project, seq0, storage=storage, run_ai_review=False
        )
        assert not report.is_exportable()
        assert any(f.rule_id == "M03" for f in report.errors())


async def test_second_sequence_lifecycle_integrity_passes_when_prior_is_available(db_factory):
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
        certificate.certificate_number = "CPP-CHANGED"
        seq1 = Sequence(project_id=project.id, number="0001")
        db.add(seq1)
        await db.commit()
        await build_ectd_sequence(db, project, seq1, storage=storage)

        report = await validate_ectd_sequence(
            db, project, seq1, storage=storage, run_ai_review=False
        )
        assert report.is_exportable()
        assert not any(f.category == "lifecycle" for f in report.findings)


async def test_ai_reviewer_failure_degrades_instead_of_breaking_the_report(db_factory):
    """The additive layer must not be able to take down the deterministic
    one -- a dead LLM becomes a visible advisory, not an exception."""
    from unittest.mock import patch

    async with db_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        storage = InMemoryStorageClient()
        await build_ectd_sequence(db, project, seq0, storage=storage)

        with patch("app.ectd.report.review_narratives", side_effect=RuntimeError("no API key")):
            report = await validate_ectd_sequence(db, project, seq0, storage=storage)

        degraded = [f for f in report.findings if f.rule_id == "AI99"]
        assert len(degraded) == 1
        assert degraded[0].severity == Severity.ADVISORY
        assert "no API key" in degraded[0].message
        assert report.is_exportable()


async def test_ai_reviewer_findings_are_advisory_and_never_block_export(pg_session_factory):
    from app.llm.client import LLMClient

    class StubLLM(LLMClient):
        def generate(self, system, messages, max_tokens=1024):
            return "ISSUE: worth a second look. [Source: Q1A(R2) v2.3]"

    async with pg_session_factory() as db:
        project = _eu_examox()
        db.add(project)
        await db.commit()

        narrative = NarrativeGeneration(
            project_id=project.id,
            section_number="3.2.P.8.1",
            slot="conclusion",
            model_name="stub",
            prompt="p",
            output="text",
            status=NarrativeStatus.APPROVED,
            final_text="text",
        )
        db.add(narrative)
        seq0 = Sequence(project_id=project.id, number="0000")
        db.add(seq0)
        await db.commit()

        storage = InMemoryStorageClient()
        await build_ectd_sequence(db, project, seq0, storage=storage)

        from unittest.mock import patch

        with patch("app.ectd.ai_review.get_llm_client", return_value=StubLLM()):
            report = await validate_ectd_sequence(db, project, seq0, storage=storage)

        ai_findings = [f for f in report.findings if f.source == "ai-reviewer"]
        assert len(ai_findings) == 1
        assert ai_findings[0].severity == Severity.ADVISORY
        assert "[Source: Q1A(R2) v2.3]" in ai_findings[0].message
        # advisory findings never gate -- report is still exportable
        # purely on the strength of a clean mechanical/data result.
        assert report.is_exportable()
