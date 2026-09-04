"""Which rules a project's human overrides currently excuse.

WHY this is one function and not three (P15c): /readiness, the CTD
builder and the eCTD builder each held an identical copy of this query.
That was harmless while an override was a row that existed forever --
and became a real hazard the moment overrides could be WITHDRAWN, since
a copy that forgot the filter would keep letting a retracted decision
open the export gate. One definition, three callers, no way for them to
disagree.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ValidationOverride


async def active_overrides(db: AsyncSession, project_id: uuid.UUID) -> list[ValidationOverride]:
    """The overrides currently standing on this project, newest last."""
    stmt = (
        select(ValidationOverride)
        .where(
            ValidationOverride.project_id == project_id,
            # A withdrawn override stops excusing its rule immediately; the
            # row stays for the audit trail (see the model's WHY).
            ValidationOverride.withdrawn_at.is_(None),
        )
        .order_by(ValidationOverride.created_at)
    )
    return list((await db.scalars(stmt)).all())


async def active_override_rule_ids(db: AsyncSession, project_id: uuid.UUID) -> frozenset[str]:
    return frozenset(o.rule_id for o in await active_overrides(db, project_id))
