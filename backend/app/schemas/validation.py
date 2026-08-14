from __future__ import annotations

from pydantic import BaseModel

from app.validation.engine import Severity


class FindingRead(BaseModel):
    rule_id: str
    severity: Severity
    category: str
    message: str
    section: str | None = None
    # P10: which layer produced this finding. Defaulted, so the P06-only
    # /readiness endpoint keeps working unchanged -- but it now carries
    # the same provenance the consolidated eCTD report does, so the UI
    # renders one shape of finding everywhere instead of two.
    source: str = "data-rule"


class ReadinessResponse(BaseModel):
    is_exportable: bool
    findings: list[FindingRead]
    overridden_rule_ids: list[str]


class ValidationOverrideCreate(BaseModel):
    rule_id: str
    reason: str


class ValidationOverrideRead(BaseModel):
    id: str
    project_id: str
    rule_id: str
    reason: str
    created_by_id: str
