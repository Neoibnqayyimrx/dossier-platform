"""Shared seed-builder plumbing."""

from __future__ import annotations

import uuid

from app.models import Product, User


def attach_owner(product: Product, owner_id: uuid.UUID | None) -> None:
    """Point `product` at its owner (Product.owner_id's WHY explains why
    Product, not Project, holds this).

    WHY a fresh User when owner_id is None: every seed builder
    (build_lamox/build_examox/build_ampiclox) is called from plain model
    tests that never touch auth at all, plus run_demo.py -- neither has a
    real logged-in user to attach. A random per-call email avoids the
    unique constraint when a test seeds more than one project in the same
    session (e.g. test_module1.py's two build_examox() calls). Callers that
    DO have a real user (the *_api.py tests, via auth_client) pass its id
    instead, so the seeded data is actually reachable through the
    ownership check.
    """
    if owner_id is not None:
        product.owner_id = owner_id
        return
    product.owner = User(
        email=f"seed-{uuid.uuid4().hex[:8]}@example.internal",
        hashed_password="unusable-seed-password-hash",
    )
