"""Results inside one batch analysis (3.2.S.4.4, 3.2.P.5.4).

WHY this is hand-written when every other child collection comes from
`build_child_router`: the factory checks ONE parent -- the one in the path.
Recording a result needs two things checked at once, and the second is the
point of the whole model:

    the specification test this result answers must belong to
    the same owner as the batch the result is being recorded on.

Without that, a well-formed request could file amoxicillin's assay result
against cloxacillin's assay limit, and every downstream check -- including
R22, which reads the limit through the test -- would then compare a number
to the wrong criterion and report a clean pass. The mistake would be
invisible in every rendered table, because both tables would look right.

The factory also cannot reach this collection's owner: `owner_via` walks
exactly one relationship to Product, and a drug-substance batch is two hops
away (BatchAnalysis -> ActiveIngredient -> Product). Generalising the
factory to walk a chain, for one caller that also needs a bespoke rule,
would have been the more complicated of the two options.

422, not 404, when the test belongs to a different owner: the test exists
and the caller may legitimately know about it -- what is wrong is the
PAIRING. A 404 would send them looking for a missing row that is right
there.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models import (
    ActiveIngredient,
    BatchAnalysis,
    BatchAnalysisResult,
    Product,
    SpecificationTest,
    User,
)
from app.schemas.batch_analysis import (
    BatchAnalysisResultCreate,
    BatchAnalysisResultRead,
    BatchAnalysisResultUpdate,
)

router = APIRouter(prefix="/batches/{batch_id}/results", tags=["batches"])


async def _get_batch_or_404(batch_id: uuid.UUID, user: User, db: AsyncSession) -> BatchAnalysis:
    """The batch, if this user owns the product it ultimately belongs to.

    Two owner paths, because a batch is a batch of the substance or of the
    finished product. Both end at the product's organization, the
    unit of access since gap Phase 6a (see app/models/organization.py).

    404, never 403: a batch belonging to someone else must look exactly
    like one that does not exist -- the same call every other router here
    makes.
    """
    batch = await db.scalar(
        select(BatchAnalysis)
        .where(BatchAnalysis.id == batch_id)
        .options(selectinload(BatchAnalysis.results))
    )
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")

    if batch.product_id is not None:
        organization_id = await db.scalar(
            select(Product.organization_id).where(Product.id == batch.product_id)
        )
    else:
        organization_id = await db.scalar(
            select(Product.organization_id)
            .join(ActiveIngredient, ActiveIngredient.product_id == Product.id)
            .where(ActiveIngredient.id == batch.active_ingredient_id)
        )
    if organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
    return batch


async def _test_in_the_batchs_specification(
    batch: BatchAnalysis, specification_test_id: uuid.UUID, db: AsyncSession
) -> SpecificationTest:
    """The specification test, if it is one of THIS batch's own tests."""
    test = await db.get(SpecificationTest, specification_test_id)
    if test is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"No specification test {specification_test_id}; a result can only be "
            f"recorded against a test that is in the specification.",
        )
    same_owner = (
        test.active_ingredient_id is not None
        and test.active_ingredient_id == batch.active_ingredient_id
    ) or (test.product_id is not None and test.product_id == batch.product_id)
    if not same_owner:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Specification test {test.test_name!r} does not belong to the material "
            f"batch {batch.batch_number!r} is a batch of, so its acceptance criterion "
            f"is not the limit this result must meet.",
        )
    return test


@router.get("", response_model=list[BatchAnalysisResultRead])
async def list_results(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batch = await _get_batch_or_404(batch_id, user, db)
    stmt = (
        select(BatchAnalysisResult).where(BatchAnalysisResult.batch_analysis_id == batch.id)
        # Specification order, so the batch table's rows line up with the
        # specification table's rows on an assessor's screen.
        .order_by(BatchAnalysisResult.sort_order)
    )
    return list((await db.scalars(stmt)).all())


@router.post("", response_model=BatchAnalysisResultRead, status_code=status.HTTP_201_CREATED)
async def create_result(
    batch_id: uuid.UUID,
    payload: BatchAnalysisResultCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batch = await _get_batch_or_404(batch_id, user, db)
    test = await _test_in_the_batchs_specification(batch, payload.specification_test_id, db)
    # One result per test per batch. A second one would give the same test
    # two answers in one batch, and nothing downstream could say which is
    # the result -- R22 would check both and the rendered table would print
    # both.
    if any(r.specification_test_id == test.id for r in batch.results):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Batch {batch.batch_number!r} already has a result for {test.test_name!r}.",
        )
    data = payload.model_dump()
    # The specification's own order wins over whatever the client sent, so
    # the two tables cannot be ordered differently (see
    # BatchAnalysisResult.sort_order's WHY).
    data["sort_order"] = test.sort_order
    result = BatchAnalysisResult(**data, batch_analysis_id=batch.id)
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return result


@router.patch("/{result_id}", response_model=BatchAnalysisResultRead)
async def update_result(
    batch_id: uuid.UUID,
    result_id: uuid.UUID,
    payload: BatchAnalysisResultUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batch = await _get_batch_or_404(batch_id, user, db)
    result = await db.scalar(
        select(BatchAnalysisResult).where(
            BatchAnalysisResult.id == result_id,
            BatchAnalysisResult.batch_analysis_id == batch.id,
        )
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such result")
    # `specification_test_id` is absent from the Update schema on purpose:
    # re-pointing a result at a different test changes which limit it is
    # judged against, which is a different measurement, not an edit. Delete
    # it and record the right one.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(result, field, value)
    await db.commit()
    await db.refresh(result)
    return result


@router.delete("/{result_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_result(
    batch_id: uuid.UUID,
    result_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batch = await _get_batch_or_404(batch_id, user, db)
    result = await db.scalar(
        select(BatchAnalysisResult).where(
            BatchAnalysisResult.id == result_id,
            BatchAnalysisResult.batch_analysis_id == batch.id,
        )
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such result")
    await db.delete(result)
    await db.commit()
