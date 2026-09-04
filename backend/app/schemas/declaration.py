"""Declaration schemas (P15a).

The signed/notarized flags are writable because they record a fact about
the physical world -- a human signed the printed document, a notary
sealed it -- that the platform cannot observe for itself. R15 blocks
export on an unsigned declaration, so these flags are the only way to
clear it, and marking one signed is a deliberate human assertion.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel

from app.models.enums import DeclarationType
from app.schemas.base import ReadMixin


class DeclarationBase(BaseModel):
    declaration_type: DeclarationType
    signed: bool = False
    signed_date: date | None = None
    notarized: bool = False
    notarization_date: date | None = None


class DeclarationCreate(DeclarationBase):
    pass


class DeclarationUpdate(BaseModel):
    declaration_type: DeclarationType | None = None
    signed: bool | None = None
    signed_date: date | None = None
    notarized: bool | None = None
    notarization_date: date | None = None


class DeclarationRead(DeclarationBase, ReadMixin):
    project_id: uuid.UUID
