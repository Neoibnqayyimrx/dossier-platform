from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

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
    # WHY a minimum length (P15c): this reason is the entire control on an
    # override -- the platform lets a known regulatory error through
    # because a human justified it. "n/a" is not a justification, and a
    # free-text field with no floor collects exactly that. Deliberately
    # modest: long enough to refuse a shrug, short enough not to invite
    # padding.
    reason: str = Field(min_length=20)


class ValidationOverrideRead(BaseModel):
    id: str
    project_id: str
    rule_id: str
    reason: str
    created_by_id: str
    # Null while the override still stands. A withdrawn one keeps its
    # original reason -- see the model's WHY.
    withdrawn_at: datetime | None = None
    withdrawn_by_id: str | None = None
