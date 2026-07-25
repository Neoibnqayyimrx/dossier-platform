"""Knowledge-base endpoints (P03): ingest a guideline, search over it.

WHY ingest requires auth but search doesn't: matches the P02 convention
already used everywhere else in this API — reads stay open, writes require
a logged-in user. There's no admin role yet (P02 deliberately didn't build
one — "don't gold-plate"), so `get_current_user` is the closest available
gate; adding a real role check is a P02-scope follow-up, not something to
improvise here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.knowledge.embeddings import get_embedding_client
from app.knowledge.ingest import KBIngestRejected, ingest_document
from app.knowledge.retrieve import search
from app.models import User
from app.schemas.kb import KBIngestRequest, KBIngestResponse, KBSearchResult

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.post("/ingest", response_model=KBIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest(
    payload: KBIngestRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> KBIngestResponse:
    settings = get_settings()
    try:
        result = await ingest_document(
            db,
            get_embedding_client(),
            source=payload.source,
            title=payload.title,
            version=payload.version,
            license=payload.license,
            text=payload.text,
            url=payload.url,
            jurisdiction=payload.jurisdiction,
            chunk_max_chars=settings.kb_chunk_max_chars,
        )
    except KBIngestRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    document = result.document
    return KBIngestResponse(
        document_id=document.id,
        source=document.source,
        title=document.title,
        version=document.version,
        license=document.license,
        url=document.url,
        jurisdiction=document.jurisdiction,
        chunks_created=result.chunks_created,
        was_update=result.was_update,
    )


@router.get("/search", response_model=list[KBSearchResult])
async def search_kb(
    q: str = Query(..., min_length=1),
    k: int | None = Query(default=None, ge=1, le=50),
    source: str | None = Query(default=None),
    jurisdiction: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[KBSearchResult]:
    settings = get_settings()
    try:
        results = await search(
            db,
            get_embedding_client(),
            q,
            k=k or settings.kb_search_default_k,
            source=source,
            jurisdiction=jurisdiction,
        )
    except ValueError as exc:
        # KBSource(source) raises ValueError for an unrecognized filter —
        # a client-side mistake (typo'd source name), not a server error.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    return [
        KBSearchResult(
            chunk_id=r.chunk_id,
            text=r.text,
            section_label=r.section_label,
            similarity=r.similarity,
            document_id=r.document_id,
            source=r.source,
            title=r.title,
            version=r.version,
            url=r.url,
            jurisdiction=r.jurisdiction,
        )
        for r in results
    ]
