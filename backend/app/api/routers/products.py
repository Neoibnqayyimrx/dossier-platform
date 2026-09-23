"""Product CRUD (AGENTS.md §6). Product is master data — not owned by a
single Project — so it gets its own top-level collection."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.loading import PRODUCT_CHILD_OPTIONS
from app.models import Product, User
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])


async def _get_product_or_404(product_id: uuid.UUID, user: User, db: AsyncSession) -> Product:
    stmt = (
        select(Product)
        .where(Product.id == product_id, Product.organization_id == user.organization_id)
        .options(*PRODUCT_CHILD_OPTIONS)
    )
    product = await db.scalar(stmt)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Product:
    # Neither owner_id nor organization_id is taken from the payload --
    # ProductCreate has no such field, so there is nothing for a client to
    # spoof here. Both come from the token's user.
    product = Product(
        **payload.model_dump(), owner_id=user.id, organization_id=user.organization_id
    )
    db.add(product)
    await db.commit()
    return await _get_product_or_404(product.id, user, db)


@router.get("", response_model=list[ProductRead])
async def list_products(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.organization_id == user.organization_id)
        .options(*PRODUCT_CHILD_OPTIONS)
    )
    return list((await db.scalars(stmt)).all())


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Product:
    return await _get_product_or_404(product_id, user, db)


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Product:
    product = await _get_product_or_404(product_id, user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.commit()
    return await _get_product_or_404(product_id, user, db)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    product = await _get_product_or_404(product_id, user, db)
    await db.delete(product)
    await db.commit()
