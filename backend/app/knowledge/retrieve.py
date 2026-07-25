"""Retrieval service for the regulatory knowledge base (P03).

WHY every result carries source/title/version/section_label: AGENTS.md §5
is explicit that retrieval which can't be cited isn't useful here — the
narrative generator (P05) and AI reviewer (P10) need to say *where* a claim
came from, not just produce text that sounds plausible. A `SearchResult`
with no way back to its document would defeat the purpose of building this
at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.embeddings import EmbeddingClient
from app.models.enums import KBSource
from app.models.kb import KBChunk, KBDocument


@dataclass
class SearchResult:
    chunk_id: str
    text: str
    section_label: str | None
    similarity: float
    document_id: str
    source: KBSource
    title: str
    version: str
    url: str | None
    jurisdiction: str | None


async def search(
    session: AsyncSession,
    embedding_client: EmbeddingClient,
    query: str,
    *,
    k: int,
    source: str | None = None,
    jurisdiction: str | None = None,
) -> list[SearchResult]:
    """Embed `query` and return the top-k most similar chunks, each carrying
    the metadata needed to cite it. `source`/`jurisdiction` narrow the
    search to a subset of the knowledge base when given."""
    (query_vector,) = embedding_client.embed([query], input_type="query")

    # pgvector's cosine_distance is 1 - cosine_similarity, so ascending
    # distance is descending similarity; converting back to similarity
    # (1 - distance) makes the score intuitive for API consumers (1.0 =
    # identical, 0.0 = orthogonal) instead of leaking a pgvector-specific
    # convention across the interface.
    distance = KBChunk.embedding.cosine_distance(query_vector)
    stmt = select(KBChunk, KBDocument, distance.label("distance")).join(
        KBDocument, KBChunk.document_id == KBDocument.id
    )
    if source is not None:
        stmt = stmt.where(KBDocument.source == KBSource(source))
    if jurisdiction is not None:
        stmt = stmt.where(KBDocument.jurisdiction == jurisdiction)
    stmt = stmt.order_by(distance).limit(k)

    rows = await session.execute(stmt)
    return [
        SearchResult(
            chunk_id=str(chunk.id),
            text=chunk.text,
            section_label=chunk.section_label,
            similarity=1.0 - dist,
            document_id=str(document.id),
            source=document.source,
            title=document.title,
            version=document.version,
            url=document.url,
            jurisdiction=document.jurisdiction,
        )
        for chunk, document, dist in rows
    ]
