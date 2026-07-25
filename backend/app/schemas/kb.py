from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import KBLicense, KBSource


class KBIngestRequest(BaseModel):
    source: str
    title: str
    version: str
    license: str
    text: str
    url: str | None = None
    jurisdiction: str | None = None


class KBIngestResponse(BaseModel):
    document_id: uuid.UUID
    source: KBSource
    title: str
    version: str
    license: KBLicense
    url: str | None
    jurisdiction: str | None
    chunks_created: int
    was_update: bool


class KBSearchResult(BaseModel):
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
