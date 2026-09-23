"""Shared seed-builder plumbing."""

from __future__ import annotations

import uuid

from app.models import Organization, Product, User


def attach_owner(product: Product, owner: User | None) -> None:
    """Give `product` its creator and its ORGANIZATION -- the unit of access
    since gap Phase 6a (see app/models/organization.py).

    WHY the User and not an id (as before 6a): a user already knows their
    organization, so one argument carries both halves and a caller can't
    pass a user from one organization with the org of another.

    WHY a fresh User AND Organization when owner is None: every seed builder
    is also called from plain model tests that never touch auth at all, plus
    run_demo.py -- neither has a real logged-in user to attach. A random
    per-call email avoids the unique constraint when a test seeds more than
    one project in the same session (e.g. test_module1.py's two
    build_examox() calls). Callers that DO have a real user (the *_api.py
    tests, via auth_client) pass it instead, so the seeded data is actually
    reachable through the ownership check.
    """
    if owner is not None:
        product.owner = owner
        # The id, not the relationship: `owner.organization` is loaded
        # (User.organization is lazy="joined"), but assigning the id avoids
        # merging a second copy of the organization into the session.
        product.organization_id = owner.organization_id
        return
    organization = Organization(name=f"seed-{uuid.uuid4().hex[:8]} organization")
    product.organization = organization
    product.owner = User(
        email=f"seed-{uuid.uuid4().hex[:8]}@example.internal",
        hashed_password="unusable-seed-password-hash",
        organization=organization,
    )


def same_owner_as(product: Product) -> dict:
    """Constructor kwargs giving another owned root -- in practice the
    project's Applicant (P15a) -- the same creator and organization as
    `product`.

    WHY it returns kwargs instead of setting the attributes: which ones to
    set depends on how the product got its owner. A seed for a real user
    holds the organization's id, while one built for a model test holds a
    transient Organization object that has no id until flush. Passing
    `organization_id` in the second case would write None.
    """
    if product.organization is not None:
        return {"owner": product.owner, "organization": product.organization}
    return {"owner": product.owner, "organization_id": product.organization_id}
