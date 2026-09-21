"""Applicant schemas (P15a).

Applicant is master data like Product -- reusable across a user's
projects -- so it gets its own top-level CRUD rather than being nested
under one Project. owner_id never appears here: it comes from the bearer
token, exactly as Product's does, so there is nothing for a client to
spoof.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.base import ReadMixin

# gap Phase 4b: nine digits and nothing else -- D-U-N-S numbers have no
# letters, dashes or spaces, and FDA's backbone wants the bare number. Checked
# here, at the boundary, because a malformed one is a typing error with a
# clear answer, not a regulatory judgement for the rule engine.
DunsNumber = Annotated[str, Field(pattern=r"^\d{9}$")]


class ApplicantBase(BaseModel):
    company_name: str
    address: str | None = None
    country: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    authorized_representative_name: str | None = None
    authorized_representative_title: str | None = None
    duns_number: DunsNumber | None = None


class ApplicantCreate(ApplicantBase):
    pass


class ApplicantUpdate(BaseModel):
    company_name: str | None = None
    address: str | None = None
    country: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    authorized_representative_name: str | None = None
    authorized_representative_title: str | None = None
    duns_number: DunsNumber | None = None


class ApplicantRead(ApplicantBase, ReadMixin):
    pass
