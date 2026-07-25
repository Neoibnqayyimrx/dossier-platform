"""Human review actions on a generated narrative (P05): approve or edit.

WHY `final_text` is set here and nowhere else: the P04 template context
builder (see context.py's wiring) only ever reads `final_text`, never
`output` directly -- so a narrative slot can reach a rendered document
only by going through one of these two functions, both of which require an
explicit human action. There is no code path that promotes a PENDING draft
to usable text on its own.
"""

from __future__ import annotations

from app.models.enums import NarrativeStatus
from app.models.narrative import NarrativeGeneration


def approve_narrative(narrative: NarrativeGeneration) -> NarrativeGeneration:
    narrative.status = NarrativeStatus.APPROVED
    narrative.final_text = narrative.output
    return narrative


def edit_narrative(narrative: NarrativeGeneration, edited_text: str) -> NarrativeGeneration:
    narrative.status = NarrativeStatus.EDITED
    narrative.final_text = edited_text
    return narrative
