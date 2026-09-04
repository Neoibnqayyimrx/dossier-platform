"""Schemas for the eCTD sequence build (P09) and validation (P10)
endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class OverrideSummaryRead(BaseModel):
    rule_id: str
    reason: str


class EctdBuildResponse(BaseModel):
    storage_key: str
    sequence_number: str
    # section_key -> lifecycle operation ("new"/"replace"/"delete") --
    # unchanged leaves never appear here at all, per app.ectd.lifecycle.
    operations: dict[str, str]
    # Same reasoning as CtdBuildResponse.overrides (P15c): a sequence built
    # over a waived ERROR must say so to whoever built it.
    overrides: list[OverrideSummaryRead] = []


class FindingRead(BaseModel):
    rule_id: str
    severity: str
    category: str
    message: str
    section: str | None
    # "data-rule" (P06) | "mechanical-ectd" | "external-validator" |
    # "ai-reviewer" -- which layer produced this finding.
    source: str


class EctdValidationResponse(BaseModel):
    sequence_number: str
    is_exportable: bool
    findings: list[FindingRead]
