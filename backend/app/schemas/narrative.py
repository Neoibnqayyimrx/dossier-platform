from __future__ import annotations

from pydantic import BaseModel

from app.models.enums import NarrativeStatus
from app.schemas.base import ReadMixin


class NarrativeEditRequest(BaseModel):
    text: str


class NarrativeRead(ReadMixin):
    project_id: str
    section_number: str
    slot: str
    model_name: str
    output: str
    warnings: list[str]
    status: NarrativeStatus
    final_text: str | None
    sources: list[str]


class NarrativeGenerateResponse(BaseModel):
    narrative: NarrativeRead
    warnings: list[str]
