"""Timepoint results inside one stability study (3.2.S.7.3, 3.2.P.8.3).

Hand-written for the same reason `batch_results.py` is -- the factory
checks ONE parent, and recording a stability result needs two things
checked at once:

    the specification test this result answers must belong to the
    same material the study is a study OF.

Without that, a well-formed request could file the finished product's
dissolution result against the drug substance's assay limit, and every
downstream check -- including R23, which reads the limit through the
test -- would compare a number to the wrong criterion and report a clean
pass. Nothing in any rendered table would look wrong.

## The one thing this router has that `batch_results.py` does not: PUT

A batch analysis is entered result by result, because a certificate of
analysis arrives one batch at a time. A stability dataset arrives as a
TABLE -- five timepoints across, eight tests down, pasted out of the
spreadsheet it has lived in since the study started. Forty POSTs to save
one paste is forty chances to half-save it, and a half-saved stability
table is worse than none: it looks complete.

So `PUT ""` replaces the study's whole result set in one transaction.
Replace, not merge, and deliberately: the grid on screen IS the study's
data, so a cell the filer cleared has to come back cleared. A merge would
leave deleted cells alive in the database and visible in 3.2.P.8.3 while
absent from the screen that is supposed to be showing it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models import (
    ActiveIngredient,
    Product,
    SpecificationTest,
    StabilityResult,
    StabilityStudy,
    User,
)
from app.schemas.stability import (
    StabilityResultCreate,
    StabilityResultRead,
    StabilityResultUpdate,
)

router = APIRouter(prefix="/stability/{study_id}/results", tags=["stability"])


async def _get_study_or_404(study_id: uuid.UUID, user: User, db: AsyncSession) -> StabilityStudy:
    """The study, if this user owns the product it ultimately belongs to.

    Two owner paths, because a study is a study of the substance (3.2.S.7)
    or of the finished product (3.2.P.8). Both end at the product's
    organization -- the unit of access since gap Phase 6a.

    404, never 403: a study belonging to someone else must look exactly
    like one that does not exist -- the call every other router here makes.
    """
    study = await db.scalar(
        select(StabilityStudy)
        .where(StabilityStudy.id == study_id)
        .options(
            selectinload(StabilityStudy.results).selectinload(StabilityResult.specification_test)
        )
    )
    if study is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stability study not found")

    if study.product_id is not None:
        organization_id = await db.scalar(
            select(Product.organization_id).where(Product.id == study.product_id)
        )
    else:
        organization_id = await db.scalar(
            select(Product.organization_id)
            .join(ActiveIngredient, ActiveIngredient.product_id == Product.id)
            .where(ActiveIngredient.id == study.active_ingredient_id)
        )
    if organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stability study not found")
    return study


async def _test_in_the_studys_specification(
    study: StabilityStudy, specification_test_id: uuid.UUID, db: AsyncSession
) -> SpecificationTest:
    """The specification test, if it is one of THIS study's material's own.

    422, not 404: the test exists and the caller may legitimately know
    about it -- what is wrong is the PAIRING. A 404 would send them looking
    for a missing row that is right there.
    """
    test = await db.get(SpecificationTest, specification_test_id)
    if test is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"No specification test {specification_test_id}; a stability result can "
            f"only be recorded against a test that is in the specification.",
        )
    same_owner = (
        test.active_ingredient_id is not None
        and test.active_ingredient_id == study.active_ingredient_id
    ) or (test.product_id is not None and test.product_id == study.product_id)
    if not same_owner:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Specification test {test.test_name!r} does not belong to the material this "
            f"stability study is of, so its acceptance criterion is not the limit this "
            f"result must meet.",
        )
    return test


async def _reload(study_id: uuid.UUID, db: AsyncSession) -> list[StabilityResult]:
    """The study's results, ordered and with their tests loaded.

    The specification test has to come back with them: `meets_criterion` is
    derived by reading the limit through it, so serializing a result that
    has not loaded it raises MissingGreenlet inside Pydantic -- far from
    the query that forgot it (app/api/loading.py's whole subject).
    """
    stmt = (
        select(StabilityResult)
        .where(StabilityResult.stability_study_id == study_id)
        .options(selectinload(StabilityResult.specification_test))
        # Timepoint first, then specification order: that is how a stability
        # table is read, and it is the order the renderer must reproduce
        # byte-identically on every build (AGENTS.md 5).
        .order_by(StabilityResult.timepoint_months, StabilityResult.sort_order)
    )
    return list((await db.scalars(stmt)).all())


@router.get("", response_model=list[StabilityResultRead])
async def list_results(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_study_or_404(study_id, user, db)
    return await _reload(study_id, db)


@router.post("", response_model=StabilityResultRead, status_code=status.HTTP_201_CREATED)
async def create_result(
    study_id: uuid.UUID,
    payload: StabilityResultCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    study = await _get_study_or_404(study_id, user, db)
    test = await _test_in_the_studys_specification(study, payload.specification_test_id, db)
    # One answer per test per timepoint. A second is not extra data, it is
    # a table with two values in one box -- and whichever renders second
    # wins silently. The database says so too (uq_stability_result_cell);
    # this turns the constraint into a message a filer can act on.
    if any(
        r.specification_test_id == test.id and r.timepoint_months == payload.timepoint_months
        for r in study.results
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This study already has a {test.test_name!r} result at "
            f"{payload.timepoint_months} months.",
        )
    data = payload.model_dump()
    # The specification's own order wins over whatever the client sent, so
    # the stability table and the specification table cannot be ordered
    # differently (see StabilityResult.sort_order's WHY).
    data["sort_order"] = test.sort_order
    result = StabilityResult(**data, stability_study_id=study.id)
    db.add(result)
    await db.commit()
    await db.refresh(result, ["specification_test"])
    return result


@router.put("", response_model=list[StabilityResultRead])
async def replace_results(
    study_id: uuid.UUID,
    payload: list[StabilityResultCreate],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replace the study's entire result set -- the grid's save, and the
    landing point for a spreadsheet paste.

    Validated in full BEFORE anything is deleted. A paste that names one
    test the specification does not contain must leave the existing table
    exactly as it was, not half-replaced: the failure mode of the other
    order is a study that loses its data to a typo.
    """
    study = await _get_study_or_404(study_id, user, db)

    tests: dict[uuid.UUID, SpecificationTest] = {}
    seen: set[tuple[uuid.UUID, int]] = set()
    for item in payload:
        if item.specification_test_id not in tests:
            tests[item.specification_test_id] = await _test_in_the_studys_specification(
                study, item.specification_test_id, db
            )
        cell = (item.specification_test_id, item.timepoint_months)
        if cell in seen:
            test = tests[item.specification_test_id]
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Two values for {test.test_name!r} at {item.timepoint_months} months. "
                f"A cell holds one result.",
            )
        seen.add(cell)

    await db.execute(delete(StabilityResult).where(StabilityResult.stability_study_id == study.id))
    for item in payload:
        test = tests[item.specification_test_id]
        db.add(
            StabilityResult(
                stability_study_id=study.id,
                specification_test_id=test.id,
                timepoint_months=item.timepoint_months,
                result=item.result,
                sort_order=test.sort_order,
            )
        )
    await db.commit()
    return await _reload(study.id, db)


@router.patch("/{result_id}", response_model=StabilityResultRead)
async def update_result(
    study_id: uuid.UUID,
    result_id: uuid.UUID,
    payload: StabilityResultUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    study = await _get_study_or_404(study_id, user, db)
    result = await db.scalar(
        select(StabilityResult)
        .where(
            StabilityResult.id == result_id,
            StabilityResult.stability_study_id == study.id,
        )
        .options(selectinload(StabilityResult.specification_test))
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such result")
    # `specification_test_id` and `timepoint_months` are absent from the
    # Update schema on purpose: either one changes which cell of the table
    # this is, which is a different measurement, not an edit. Delete it and
    # record the right one.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(result, field, value)
    await db.commit()
    await db.refresh(result, ["specification_test"])
    return result


@router.delete("/{result_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_result(
    study_id: uuid.UUID,
    result_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    study = await _get_study_or_404(study_id, user, db)
    result = await db.scalar(
        select(StabilityResult).where(
            StabilityResult.id == result_id,
            StabilityResult.stability_study_id == study.id,
        )
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such result")
    await db.delete(result)
    await db.commit()
