"""Specification test schemas.

P20: the owner columns are all READ-only here, and deliberately so. A
specification row is created through its owner's endpoint
(`/apis/{id}/specification`, `/products/{id}/specification`,
`/excipients/{id}/specification`), so the owner comes from the URL path,
never from the request body. A create payload that could name its own
owner would let a caller file a specification against someone else's
excipient with a well-formed request -- the ownership check
(app/api/routers/product_children.py) is on the PARENT in the path, so the
path is the only trustworthy place for the owner to come from.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import SpecificationOwnerKind
from app.schemas.base import ReadMixin


class SpecificationTestBase(BaseModel):
    test_name: str
    method: str
    acceptance_criterion: str
    sort_order: int = 0
    notes: str | None = None


class SpecificationTestCreate(SpecificationTestBase):
    pass


class SpecificationTestUpdate(BaseModel):
    test_name: str | None = None
    method: str | None = None
    acceptance_criterion: str | None = None
    sort_order: int | None = None
    notes: str | None = None


class SpecificationTestRead(SpecificationTestBase, ReadMixin):
    # All three, all optional, exactly one set -- the shape of the table.
    # Kept as raw ids rather than collapsed into one `owner_id` field so a
    # client can tell WHICH kind of thing it is looking at without a second
    # request; `owner_kind` below says the same thing in one word.
    active_ingredient_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    excipient_id: uuid.UUID | None = None
    # Derived on the model from whichever FK is set (see
    # app/models/spec_owner.py). Serialising it means the frontend's one
    # editor can label itself "3.2.S.4.1" or "3.2.P.5.1" without
    # re-deriving the rule.
    owner_kind: SpecificationOwnerKind
