"""Knowledge-base documents and chunks for the RAG layer (P03).

WHY two tables, not one: `KBDocument` is metadata about a whole guideline
(source, license, version) — the unit a human judges trust in. `KBChunk` is
the retrievable unit — one embedding per chunk, not per document, so a
search can point at a specific paragraph rather than "somewhere in this
24-page PDF". Every chunk keeps a foreign key back to its document so a
retrieved result can always be cited to source + section (AGENTS.md §5:
retrieval that can't be cited is not useful here).

WHY the embedding dimension is a hard-coded constant, not read from
Settings: pgvector fixes a column's vector width at the type level — it's
part of the schema, not runtime config. Switching `embedding_model` to one
with a different output size means a new migration (a new column, backfill,
swap), not an env var change. Keep this constant equal to the current
`embedding_model`'s output size (voyage-3-lite -> 512).
"""

from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import KBLicense, KBSource

EMBEDDING_DIMENSION = 512


class KBDocument(Base):
    __tablename__ = "kb_document"

    source: Mapped[KBSource] = mapped_column(SAEnum(KBSource))
    title: Mapped[str] = mapped_column(String(300))
    version: Mapped[str] = mapped_column(String(60))  # e.g. "Q1A(R2)", "Step 4, 2003-02-06"
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    license: Mapped[KBLicense] = mapped_column(SAEnum(KBLicense))
    jurisdiction: Mapped[str | None] = mapped_column(String(60), nullable=True)

    chunks: Mapped[list["KBChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KBChunk.ordinal",
    )


class KBChunk(Base):
    __tablename__ = "kb_chunk"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("kb_document.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    section_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION))

    document: Mapped["KBDocument"] = relationship(back_populates="chunks")
