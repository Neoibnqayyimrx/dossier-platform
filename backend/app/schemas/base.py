"""Shared Pydantic base classes.

WHY a shared ReadMixin: every entity's `Read` schema needs the same three
server-generated fields (id, created_at, updated_at) and the same
`from_attributes=True` config so it can be built directly from a SQLAlchemy
ORM instance (`Model.model_validate(orm_obj)`), not just a dict.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ReadMixin(ORMBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
