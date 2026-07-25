"""Fetch approved narrative for a section, in the shape P04's template
context expects (P05).

Kept separate from `app.templating.context`, deliberately: that module is
pure and synchronous (it only reads already-loaded Project/Product objects)
precisely so P04's own tests never need an async session. Approved
narrative requires an async query against `NarrativeGeneration`, so
fetching it is a distinct step a caller (P07/P08 assembly, a script, a
route) runs first and feeds into `render_section(..., narrative=...)` --
"find the approved text" and "render a template" stay two composable
steps, not one function secretly doing both.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NarrativeStatus
from app.models.narrative import NarrativeGeneration


async def get_approved_narrative(
    db: AsyncSession, project_id: uuid.UUID, section_number: str
) -> dict[str, str]:
    """Return `{slot: final_text}` for every slot of `section_number` that
    has at least one reviewed (APPROVED or EDITED) generation on file --
    the most recent one, if a slot was regenerated and re-reviewed more
    than once. A slot with no reviewed generation is simply absent from
    the result, so `build_context`'s `narrative.get(slot) or '[[...]]'`
    falls back to the placeholder -- a PENDING draft can never reach a
    rendered document this way, only ever silence (the placeholder)."""
    stmt = (
        select(NarrativeGeneration)
        .where(
            NarrativeGeneration.project_id == project_id,
            NarrativeGeneration.section_number == section_number,
            NarrativeGeneration.status != NarrativeStatus.PENDING,
        )
        .order_by(NarrativeGeneration.created_at)
    )
    rows = (await db.scalars(stmt)).all()
    return {row.slot: row.final_text for row in rows if row.final_text is not None}
