"""Tests for the P03 knowledge base: ingestion gate, idempotency, and
retrieval.

Most of this suite runs on the same in-memory SQLite used everywhere else
(`session_factory` from conftest.py) — the allowlist gate and re-ingest
idempotency are pure relational logic and don't touch pgvector-specific
SQL. The one test that genuinely needs real Postgres is the search
round-trip, because `KBChunk.embedding.cosine_distance(...)` compiles to
the pgvector `<=>` operator, which has no SQLite equivalent. That test gets
its own throwaway Postgres database via the shared `pg_session_factory`
fixture (tests/conftest.py), which skips itself if no Postgres is
reachable — so `pytest -q` still passes for anyone without
`docker compose up -d db` running, while CI's pgvector service container
always provides one.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.knowledge.embeddings import FakeEmbeddingClient
from app.knowledge.ingest import KBIngestRejected, ingest_document
from app.knowledge.retrieve import search
from app.models.kb import KBDocument

EMBEDDER = FakeEmbeddingClient()

Q1A_EXCERPT = """\
2.1.6. Testing Frequency
For long term studies, frequency of testing should be sufficient to
establish the stability profile of the drug substance.

2.1.7. Storage Conditions
In general, a drug substance should be evaluated under storage conditions
that test its thermal stability and, if applicable, its sensitivity to
moisture.
"""


async def test_ingest_rejects_disallowed_source(session_factory):
    async with session_factory() as session:
        with pytest.raises(KBIngestRejected, match="not on the knowledge-base allowlist"):
            await ingest_document(
                session,
                EMBEDDER,
                source="USP",
                title="USP Monograph: Amoxicillin",
                version="2024",
                license="public-domain",
                text="monograph text",
                chunk_max_chars=500,
            )


async def test_ingest_rejects_disallowed_license(session_factory):
    async with session_factory() as session:
        with pytest.raises(KBIngestRejected, match="not a recognized redistributable license"):
            await ingest_document(
                session,
                EMBEDDER,
                source="ICH",
                title="Q1A(R2)",
                version="Step 4, 2003-02-06",
                license="all-rights-reserved",
                text="guideline text",
                chunk_max_chars=500,
            )


async def test_reingest_replaces_rather_than_duplicates(session_factory):
    async with session_factory() as session:
        first = await ingest_document(
            session,
            EMBEDDER,
            source="ICH",
            title="Q1A(R2) Stability Testing",
            version="Step 4, 2003-02-06",
            license="ich-harmonised-guideline",
            text=Q1A_EXCERPT,
            chunk_max_chars=200,
        )
        second = await ingest_document(
            session,
            EMBEDDER,
            source="ICH",
            title="Q1A(R2) Stability Testing",
            version="Step 4, 2003-02-06",
            license="ich-harmonised-guideline",
            text=Q1A_EXCERPT,
            chunk_max_chars=200,
        )

        assert first.was_update is False
        assert second.was_update is True
        assert first.chunks_created == second.chunks_created

        documents = (await session.scalars(sa.select(KBDocument))).all()
        assert len(documents) == 1
        assert len(documents[0].chunks) == second.chunks_created


async def test_ingest_and_search_round_trip(pg_session_factory):
    async with pg_session_factory() as session:
        await ingest_document(
            session,
            EMBEDDER,
            source="ICH",
            title="Q1A(R2) Stability Testing",
            version="Step 4, 2003-02-06",
            license="ich-harmonised-guideline",
            url="https://database.ich.org/sites/default/files/Q1A(R2)%20Guideline.pdf",
            jurisdiction="ICH",
            text=Q1A_EXCERPT,
            chunk_max_chars=200,
        )
        await ingest_document(
            session,
            EMBEDDER,
            source="ICH",
            title="M4Q(R1) CTD Quality",
            version="Step 4, 2002-09-12",
            license="ich-harmonised-guideline",
            jurisdiction="ICH",
            text="This section describes the folder structure and table of "
            "contents conventions for Module 3 quality documentation.",
            chunk_max_chars=200,
        )

        results = await search(
            session, EMBEDDER, "testing frequency for long term stability studies", k=3
        )

        assert results
        assert results[0].title == "Q1A(R2) Stability Testing"
        assert results[0].section_label == "2.1.6. Testing Frequency"
        assert results[0].source.value == "ICH"

        filtered = await search(session, EMBEDDER, "testing frequency", k=3, jurisdiction="EMA")
        assert filtered == []
