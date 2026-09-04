"""Certificate schemas (P15a).

WHY every field but the type is optional: a Certificate row exists
BEFORE the real document does -- "we need a CPP, still pending" is a
legitimate state the rules are meant to report on (R13 checks the expiry
date, not merely the row). Requiring a certificate number up front would
force people to invent one, which is worse than a recorded gap.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel

from app.models.enums import CertificateType
from app.schemas.base import ReadMixin


class CertificateBase(BaseModel):
    certificate_type: CertificateType
    issuing_authority: str | None = None
    certificate_number: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    # Site-specific certificates (GMP) name a Manufacturer; a CPP or CEP
    # is about the product generally, so this stays optional.
    manufacturer_id: uuid.UUID | None = None


class CertificateCreate(CertificateBase):
    pass


class CertificateUpdate(BaseModel):
    certificate_type: CertificateType | None = None
    issuing_authority: str | None = None
    certificate_number: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    manufacturer_id: uuid.UUID | None = None


class CertificateRead(CertificateBase, ReadMixin):
    product_id: uuid.UUID
