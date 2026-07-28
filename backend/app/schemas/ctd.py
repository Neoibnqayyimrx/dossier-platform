"""Schemas for the CTD build endpoint (P08)."""

from __future__ import annotations

from pydantic import BaseModel


class PackagedFileRead(BaseModel):
    path: str
    md5: str


class CtdBuildResponse(BaseModel):
    storage_key: str
    files: list[PackagedFileRead]
