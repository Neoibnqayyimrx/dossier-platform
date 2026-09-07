"""The confidence intervals inside one bioequivalence study (P22).

Hand-written rather than built from `product_children.build_child_router`,
and for one reason that is worth stating: **a bioequivalence result set is
entered as a set, not row by row.**

A study report states Cmax, AUC(0-t) and AUC(0-inf) together, in one table,
and a filer transcribing them is copying three lines off one page. The
factory's POST-per-row shape would make that three requests that can
half-succeed -- and a study holding two of its three intervals is worse
than one holding none, because it looks answered. `PUT ""` replaces the
whole set in one transaction, the same call `stability_results.py` makes
for the same reason at forty times the scale.

The other half of that decision: replace, not merge. The three parameters
on screen ARE the study's results, so a parameter the filer removed has to
be gone from 1.4.1 and 5.2 as well.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import (
    BioequivalenceResult,
    BioequivalenceStudy,
    PKParameter,
    Product,
    User,
)
from app.schemas.bioequivalence import BioequivalenceResultCreate, BioequivalenceResultRead

router = APIRouter(prefix="/bioequivalence/{study_id}/results", tags=["bioequivalence"])

# The order every bioequivalence report and every agency form prints these
# in: rate of absorption first, then extent. Stored as `sort_order` at
# write time so the relationship can order without the renderers each
# choosing a sort key -- see BioequivalenceResult.sort_order.
_PARAMETER_ORDER = {parameter: index for index, parameter in enumerate(PKParameter)}


async def _get_study_or_404(
    study_id: uuid.UUID, user: User, db: AsyncSession
) -> BioequivalenceStudy:
    """The study, if this user owns the product it belongs to.

    404, never 403: a study belonging to someone else must look exactly
    like one that does not exist -- the call every other router here makes.
    """
    study = await db.scalar(
        select(BioequivalenceStudy)
        .join(Product, Product.id == BioequivalenceStudy.product_id)
        .where(BioequivalenceStudy.id == study_id, Product.owner_id == user.id)
    )
    if study is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bioequivalence study not found")
    return study


async def _reload(study_id: uuid.UUID, db: AsyncSession) -> list[BioequivalenceResult]:
    stmt = (
        select(BioequivalenceResult)
        .where(BioequivalenceResult.bioequivalence_study_id == study_id)
        .order_by(BioequivalenceResult.sort_order)
    )
    return list((await db.scalars(stmt)).all())


@router.get("", response_model=list[BioequivalenceResultRead])
async def list_results(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_study_or_404(study_id, user, db)
    return await _reload(study_id, db)


@router.put("", response_model=list[BioequivalenceResultRead])
async def replace_results(
    study_id: uuid.UUID,
    payload: list[BioequivalenceResultCreate],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replace the study's whole result set.

    Validated in full BEFORE anything is deleted, exactly as the stability
    grid's PUT is: a submission naming one parameter twice must leave the
    existing intervals untouched rather than half-replaced.
    """
    study = await _get_study_or_404(study_id, user, db)

    seen: set[PKParameter] = set()
    for item in payload:
        if item.parameter in seen:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Two confidence intervals for {item.parameter.value}. A study reports "
                f"one interval per parameter.",
            )
        seen.add(item.parameter)
        # A bound the wrong way round is almost always a transposed paste,
        # and it matters: `outside()` compares the lower bound against the
        # window's floor and the upper against its ceiling, so a swapped
        # pair could be reported as passing when the real interval fails.
        if item.ci_lower > item.ci_upper:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{item.parameter.value}: the lower bound ({item.ci_lower}) is above the "
                f"upper bound ({item.ci_upper}).",
            )

    await db.execute(
        delete(BioequivalenceResult).where(BioequivalenceResult.bioequivalence_study_id == study.id)
    )
    for item in payload:
        db.add(
            BioequivalenceResult(
                bioequivalence_study_id=study.id,
                sort_order=_PARAMETER_ORDER[item.parameter],
                **item.model_dump(),
            )
        )
    await db.commit()
    return await _reload(study.id, db)
