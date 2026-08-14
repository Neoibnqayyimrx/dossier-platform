"""The CTD section registry, served to the frontend (P11c).

WHY this endpoint rather than the UI listing sections itself: which
sections exist, what they're called, and which narrative slots each one
offers is decided in exactly one place --
`app.templating.registry.SECTIONS`, whose docstring makes the point that
"what sections exist and what they need" should live in one typed place.
A hand-maintained copy in the frontend would mean registering a new
section (P04's open/closed payoff -- the QOS interlude added one with
zero code changes) silently failed to show up in the review UI.

Same reasoning as `app/api/routers/enums.py`: derive, never duplicate.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.templating.registry import SECTIONS

router = APIRouter(prefix="/sections", tags=["sections"])


class SectionRead(BaseModel):
    number: str
    title: str
    # Empty for a data-only section -- section 1.2 (Registration Form) has
    # no slots at all, because every fact on it is already structured data
    # and there is nothing for the LLM to draft.
    narrative_slots: list[str]


@router.get("", response_model=list[SectionRead])
async def list_sections() -> list[SectionRead]:
    return [
        SectionRead(
            number=spec.number,
            title=spec.title,
            narrative_slots=list(spec.narrative_slots),
        )
        for spec in SECTIONS.values()
    ]
