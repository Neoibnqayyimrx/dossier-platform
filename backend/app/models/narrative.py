"""NarrativeGeneration (P05): the audit trail AGENTS.md §5 requires for
every piece of LLM-written prose — "everything the LLM writes is
reviewable" is a promise this table exists to keep.

WHY a many-to-many to KBChunk (not a JSON list of ids, not a link to
KBDocument): a relational foreign key is something the database itself
enforces (a row here provably points at a chunk that really exists and was
really retrieved), whereas a JSON blob is just a string the app promises to
interpret correctly. Linking to the chunk rather than the document keeps
the audit trail precise — which passages actually went into the prompt, not
just which guideline.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, ForeignKey, Table, Column, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import NarrativeStatus

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.kb import KBChunk

narrative_generation_source = Table(
    "narrative_generation_source",
    Base.metadata,
    Column("narrative_generation_id", ForeignKey("narrative_generation.id"), primary_key=True),
    Column("kb_chunk_id", ForeignKey("kb_chunk.id"), primary_key=True),
)


class NarrativeGeneration(Base):
    __tablename__ = "narrative_generation"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"))
    section_number: Mapped[str] = mapped_column(String(20))
    slot: Mapped[str] = mapped_column(String(60))

    model_name: Mapped[str] = mapped_column(String(80))
    prompt: Mapped[str] = mapped_column(Text)
    output: Mapped[str] = mapped_column(Text)
    # newline-joined guardrail warnings (e.g. numeric leakage) -- a plain
    # audit note for a human reviewer, never parsed back by code, so a
    # delimited string is enough; no need for a separate table.
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[NarrativeStatus] = mapped_column(
        SAEnum(NarrativeStatus), default=NarrativeStatus.PENDING
    )
    # set by approve() (copy of `output`) or edit() (human-provided text).
    # The template context builder (P04) must read THIS, never `output`
    # directly, so an edited correction can never be silently bypassed.
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="narrative_generations")
    sources: Mapped[list["KBChunk"]] = relationship(secondary=narrative_generation_source)
