"""Factory for nested child resources — each is mounted under its parent
(`/products/{product_id}/...`, `/apis/{active_ingredient_id}/...`) because
none of them make sense detached from that parent, and each is otherwise an
identical CRUD shape. One factory instead of N near-duplicate router files.

WHY the parent is parameterized rather than hard-coded to Product: the
drug-substance specification (3.2.S.4.1) hangs off an ActiveIngredient, not
a Product, since a fixed-dose combination has one specification PER ACTIVE.
That was the first child whose parent wasn't Product, and generalizing the
existing factory was cheaper and less duplicative than writing a second one
that differed only in which foreign key it filtered on.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    parent_model: type[Base] = Product,
    parent_segment: str = "products",
    parent_fk: str = "product_id",
    order_by: str | None = None,
    nested_collections: tuple[str, ...] = (),
) -> APIRouter:
    parent_name = parent_model.__name__
    # WHY: any relationship the READ schema nests must be eager-loaded, or
    # serializing it raises MissingGreenlet on the async engine (see
    # app/api/loading.py). The factory has to do this itself -- a router
    # built here returns rows straight from its own queries, so the
    # centralized options in loading.py never reach them.
    _load = tuple(selectinload(getattr(model, name)) for name in nested_collections)
    router = APIRouter(prefix=f"/{parent_segment}/{{parent_id}}/{resource}", tags=[resource])

    async def _get_parent_or_404(parent_id: uuid.UUID, db: AsyncSession) -> None:
        if await db.scalar(select(parent_model.id).where(parent_model.id == parent_id)) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{parent_name} not found")

    async def _get_child_or_404(parent_id: uuid.UUID, child_id: uuid.UUID, db: AsyncSession) -> Any:
        stmt = (
            select(model)
            .where(model.id == child_id, getattr(model, parent_fk) == parent_id)
            .options(*_load)
        )
        obj = await db.scalar(stmt)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such {resource} record")
        return obj

    @router.post("", response_model=read_schema, status_code=status.HTTP_201_CREATED)
    async def create_child(
        parent_id: uuid.UUID,
        payload: create_schema,  # type: ignore[valid-type]
        db: AsyncSession = Depends(get_db),
        _user: User = Depends(get_current_user),
    ):
        await _get_parent_or_404(parent_id, db)
        obj = model(**payload.model_dump(), **{parent_fk: parent_id})
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        # A second, targeted refresh: passing attribute_names to the first
        # one would LIMIT it to those attributes, leaving server-side
        # columns like updated_at expired and unloadable.
        if nested_collections:
            await db.refresh(obj, nested_collections)
        return obj

    @router.get("", response_model=list[read_schema])
    async def list_children(parent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
        await _get_parent_or_404(parent_id, db)
        stmt = select(model).where(getattr(model, parent_fk) == parent_id).options(*_load)
        # WHY an explicit order: without one Postgres may return rows in any
        # order, and a specification table whose rows shuffle between reads
        # would break both the reviewer's eye and the byte-identical-rebuild
        # guarantee (AGENTS.md §5).
        if order_by is not None:
            stmt = stmt.order_by(getattr(model, order_by))
        return list((await db.scalars(stmt)).all())

    @router.get("/{child_id}", response_model=read_schema)
    async def get_child(
        parent_id: uuid.UUID, child_id: uuid.UUID, db: AsyncSession = Depends(get_db)
    ):
        return await _get_child_or_404(parent_id, child_id, db)

    @router.patch("/{child_id}", response_model=read_schema)
    async def update_child(
        parent_id: uuid.UUID,
        child_id: uuid.UUID,
        payload: update_schema,  # type: ignore[valid-type]
        db: AsyncSession = Depends(get_db),
        _user: User = Depends(get_current_user),
    ):
        obj = await _get_child_or_404(parent_id, child_id, db)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        await db.commit()
        await db.refresh(obj)
        # A second, targeted refresh: passing attribute_names to the first
        # one would LIMIT it to those attributes, leaving server-side
        # columns like updated_at expired and unloadable.
        if nested_collections:
            await db.refresh(obj, nested_collections)
        return obj

    @router.delete("/{child_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_child(
        parent_id: uuid.UUID,
        child_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
        _user: User = Depends(get_current_user),
    ):
        obj = await _get_child_or_404(parent_id, child_id, db)
        await db.delete(obj)
        await db.commit()

    return router
