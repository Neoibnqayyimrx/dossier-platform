"""Impurity schemas (3.2.S.3.2, 3.2.P.5.5)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import ImpurityType, SpecificationOwnerKind
from app.schemas.base import ReadMixin


class ImpurityBase(BaseModel):
    name: str
    impurity_type: ImpurityType
    limit: str | None = None
    # A citation, never the source's text (AGENTS.md §5). Rule R11 reads
    # this string looking for a pharmacopoeial reference, which is how the
    # version reminder reaches impurity limits.
    limit_source: str | None = None
    smiles: str | None = None
    origin: str | None = None


class ImpurityCreate(ImpurityBase):
    pass


class ImpurityUpdate(BaseModel):
    name: str | None = None
    impurity_type: ImpurityType | None = None
    limit: str | None = None
    limit_source: str | None = None
    smiles: str | None = None
    origin: str | None = None


class ImpurityRead(ImpurityBase, ReadMixin):
    active_ingredient_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    owner_kind: SpecificationOwnerKind
