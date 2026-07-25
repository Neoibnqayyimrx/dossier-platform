"""Ingestion pipeline for the regulatory knowledge base (P03).

WHY the license/source gate lives here, as code, rather than as a process
rule ("only ingest ICH docs, promise"): AGENTS.md §5 calls pharmacopoeia
ingestion a hard rule, and this project's whole philosophy is that anything
a human could get wrong by hand should be something the code refuses to
do. `KBSource`/`KBLicense` (app/models/enums.py) ARE the allowlist — there
is no member for USP/Ph. Eur./BP/JP, so constructing one from a disallowed
string raises before a single row is written.

WHY idempotent-by-replace, not diff: re-ingesting the same (source, title,
version) deletes and rebuilds that document's chunks rather than trying to
match old chunks to new ones. A guideline's chunking/embedding is cheap to
redo and a diff would be genuinely hard to get right (chunk boundaries
shift when the source text changes even slightly); "delete and rebuild"
is the simplest thing that is still correct.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.knowledge.chunking import chunk_text
from app.knowledge.embeddings import EmbeddingClient
from app.models.enums import KBLicense, KBSource
from app.models.kb import KBChunk, KBDocument


class KBIngestRejected(ValueError):
    """Raised when a document fails the source/license allowlist gate."""


@dataclass
class IngestResult:
    document: KBDocument
    chunks_created: int
    was_update: bool


def _validate_source(source: str) -> KBSource:
    try:
        return KBSource(source)
    except ValueError:
        allowed = ", ".join(s.value for s in KBSource)
        raise KBIngestRejected(
            f"source {source!r} is not on the knowledge-base allowlist; "
            f"permitted sources: {allowed}. Pharmacopoeia bodies (USP, "
            "Ph. Eur., BP, JP) are deliberately excluded — see AGENTS.md §5."
        )


def _validate_license(license: str) -> KBLicense:
    try:
        return KBLicense(license)
    except ValueError:
        allowed = ", ".join(v.value for v in KBLicense)
        raise KBIngestRejected(
            f"license {license!r} is not a recognized redistributable "
            f"license; permitted values: {allowed}."
        )


async def ingest_document(
    session: AsyncSession,
    embedding_client: EmbeddingClient,
    *,
    source: str,
    title: str,
    version: str,
    license: str,
    text: str,
    url: str | None = None,
    jurisdiction: str | None = None,
    chunk_max_chars: int,
) -> IngestResult:
    """Reject disallowed source/license, then chunk + embed + store `text`.

    Re-ingesting the same (source, title, version) replaces that document's
    chunks in place rather than creating a duplicate document row.
    """
    source_enum = _validate_source(source)
    license_enum = _validate_license(license)

    existing = await session.scalar(
        select(KBDocument).where(
            KBDocument.source == source_enum,
            KBDocument.title == title,
            KBDocument.version == version,
        )
        # WHY selectinload: async SQLAlchemy can't lazy-load a relationship
        # outside the query that fetched it (same trap as the P02 API
        # routers hit — see build-log.md). We're about to call
        # `document.chunks.clear()` below, so the collection must already
        # be loaded.
        .options(selectinload(KBDocument.chunks))
    )

    if existing is not None:
        document = existing
        document.url = url
        document.license = license_enum
        document.jurisdiction = jurisdiction
        document.chunks.clear()
    else:
        document = KBDocument(
            source=source_enum,
            title=title,
            version=version,
            url=url,
            license=license_enum,
            jurisdiction=jurisdiction,
        )
        session.add(document)

    pieces = chunk_text(text, max_chars=chunk_max_chars)
    if pieces:
        vectors = embedding_client.embed([piece.text for piece in pieces], input_type="document")
        for ordinal, (piece, vector) in enumerate(zip(pieces, vectors)):
            document.chunks.append(
                KBChunk(
                    ordinal=ordinal,
                    text=piece.text,
                    section_label=piece.section_label,
                    embedding=vector,
                )
            )

    await session.commit()
    return IngestResult(
        document=document, chunks_created=len(pieces), was_update=existing is not None
    )
