"""Factory for the six Product child resources (manufacturers, APIs,
excipients, packaging, stability, clinical) — each is nested under
`/products/{product_id}/...` because none of them make sense detached from a
product, and each is otherwise an identical CRUD shape. One factory instead
of six near-duplicate router files.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import Product, User
from app.models.base import Base


def build_child_router(
    *,
    resource: str,
    model: type[Base],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    read_schema: type[BaseModel],
) -> APIRouter:
    router = APIRouter(prefix=f"/products/{{product_id}}/{resource}", tags=[resource])

    async def _get_product_or_404(product_id: uuid.UUID, db: AsyncSession) -> None:
        if await db.scalar(select(Product.id).where(Product.id == product_id)) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    async def _get_child_or_404(product_id: uuid.UUID, child_id: uuid.UUID, db: AsyncSession) -> Any:
        stmt = select(model).where(model.id == child_id, model.product_id == product_id)
        obj = await db.scalar(stmt)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such {resource} record")
        return obj

    @router.post("", response_model=read_schema, status_code=status.HTTP_201_CREATED)
    async def create_child(
        product_id: uuid.UUID,
        payload: create_schema,  # type: ignore[valid-type]
        db: AsyncSession = Depends(get_db),
        _user: User = Depends(get_current_user),
    ):
        await _get_product_or_404(product_id, db)
        obj = model(**payload.model_dump(), product_id=product_id)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    @router.get("", response_model=list[read_schema])
    async def list_children(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
        await _get_product_or_404(product_id, db)
        stmt = select(model).where(model.product_id == product_id)
        return list((await db.scalars(stmt)).all())

    @router.get("/{child_id}", response_model=read_schema)
    async def get_child(
        product_id: uuid.UUID, child_id: uuid.UUID, db: AsyncSession = Depends(get_db)
    ):
        return await _get_child_or_404(product_id, child_id, db)

    @router.patch("/{child_id}", response_model=read_schema)
    async def update_child(
        product_id: uuid.UUID,
        child_id: uuid.UUID,
        payload: update_schema,  # type: ignore[valid-type]
        db: AsyncSession = Depends(get_db),
        _user: User = Depends(get_current_user),
    ):
        obj = await _get_child_or_404(product_id, child_id, db)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        await db.commit()
        await db.refresh(obj)
        return obj

    @router.delete("/{child_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_child(
        product_id: uuid.UUID,
        child_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
        _user: User = Depends(get_current_user),
    ):
        obj = await _get_child_or_404(product_id, child_id, db)
        await db.delete(obj)
        await db.commit()

    return router
