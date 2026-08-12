"""Schemas for the eCTD sequence build endpoint (P09)."""

from __future__ import annotations

from pydantic import BaseModel


class EctdBuildResponse(BaseModel):
    storage_key: str
    sequence_number: str
    # section_key -> lifecycle operation ("new"/"replace"/"delete") --
    # unchanged leaves never appear here at all, per app.ectd.lifecycle.
    operations: dict[str, str]
