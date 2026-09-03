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
    # WHY this instead of a `Product`-only ownership check: Product is the
    # only model with an owner_id column (see its WHY), but ActiveIngredient
    # is one hop away from it. Naming the relationship attribute to walk
    # ("product") lets one factory cover both without hard-coding either
    # parent shape. Every parent_model this factory is ever called with is
    # either Product itself (owner_via=None) or exactly one hop from it.
    owner_via: str | None = None,
) -> APIRouter:
    parent_name = parent_model.__name__
    if parent_model is not Product and owner_via is None:
        raise TypeError(
            f"build_child_router({resource!r}): parent_model={parent_name} "
            "is not Product, so owner_via must name the relationship to it"
        )

    # WHY: any relationship the READ schema nests must be eager-loaded, or
    # serializing it raises MissingGreenlet on the async engine (see
    # app/api/loading.py). The factory has to do this itself -- a router
    # built here returns rows straight from its own queries, so the
    # centralized options in loading.py never reach them.
    _load = tuple(selectinload(getattr(model, name)) for name in nested_collections)
    router = APIRouter(prefix=f"/{parent_segment}/{{parent_id}}/{resource}", tags=[resource])

    async def _get_parent_or_404(parent_id: uuid.UUID, user: User, db: AsyncSession) -> None:
        stmt = select(parent_model.id)
        if owner_via is None:
            stmt = stmt.where(parent_model.id == parent_id, parent_model.owner_id == user.id)
        else:
            stmt = stmt.join(getattr(parent_model, owner_via)).where(
                parent_model.id == parent_id, Product.owner_id == user.id
            )
        # 404, not 403: a parent belonging to someone else should look
        # indistinguishable from one that doesn't exist (same reasoning as
        # require_project_owner).
        if await db.scalar(stmt) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{parent_name} not found")

    async def _get_child_or_404(
        parent_id: uuid.UUID, child_id: uuid.UUID, user: User, db: AsyncSession
    ) -> Any:
        # Ownership is always checked through the parent -- a child row has
        # no owner_id of its own, and never needs one.
        await _get_parent_or_404(parent_id, user, db)
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
        user: User = Depends(get_current_user),
    ):
        await _get_parent_or_404(parent_id, user, db)
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
    async def list_children(
        parent_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ):
        await _get_parent_or_404(parent_id, user, db)
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
        parent_id: uuid.UUID,
        child_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ):
        return await _get_child_or_404(parent_id, child_id, user, db)

    @router.patch("/{child_id}", response_model=read_schema)
    async def update_child(
        parent_id: uuid.UUID,
        child_id: uuid.UUID,
        payload: update_schema,  # type: ignore[valid-type]
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ):
        obj = await _get_child_or_404(parent_id, child_id, user, db)
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
        user: User = Depends(get_current_user),
    ):
        obj = await _get_child_or_404(parent_id, child_id, user, db)
        await db.delete(obj)
        await db.commit()

    return router
