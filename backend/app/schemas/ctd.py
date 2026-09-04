"""Schemas for the CTD build endpoint (P08)."""

from __future__ import annotations

from pydantic import BaseModel


class PackagedFileRead(BaseModel):
    path: str
    md5: str


class OverrideSummaryRead(BaseModel):
    rule_id: str
    reason: str


class CtdBuildResponse(BaseModel):
    storage_key: str
    files: list[PackagedFileRead]
    # WHY the build reports these (P15c): a package assembled over a waived
    # ERROR looks exactly like one that passed cleanly. The override lived
    # only in the database, so whoever downloaded the ZIP had no way to
    # know a deterministic check had been set aside for it.
    #
    # WHY they are NOT written into the package itself, which the P15 plan
    # first proposed: the ZIP is what goes to the regulator, and an
    # internal deviation record is not submission content -- it is a
    # quality record that belongs to the applicant. Surfacing it to the
    # person exporting is the control; shipping it to the agency would be
    # a different (and unasked-for) disclosure.
    overrides: list[OverrideSummaryRead] = []
