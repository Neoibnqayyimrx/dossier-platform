"""Seed the EXAMOX demo product + project into the running Postgres (P01 task 5).

EXAMOX (Amoxicillin 500 mg hard gelatin capsules, manufactured by Exagon,
Gwagwalada, Abuja) is our own company's real label facts — replaces the
earlier third-party "Parazon" placeholder. The build shares its structure
with app/seed/lamox.py (see that module and reference/worked-example-lamox.md):
a buggy 3.2.P.1 narrative (wrong strength, wrong dosage-form word, leftover
foreign-product reference) so the P06 rules R01-R03 still have real fixture
material to catch, plus a corrected variant for a clean pass.

Idempotent: re-running looks up the "EXAMOX renewal" project by name and
skips the insert if it already exists, rather than creating a duplicate.

WHY it takes an owner: since P14a every Product belongs to a User, and
the API only ever shows you your own (see app/models/product.py's WHY).
Seeding without an owner still "works" -- app.seed.attach_owner invents a
placeholder account for the model tests that have no real user -- but the
result is a demo project nobody can log in and see, which is exactly the
opposite of what a demo is for. Naming a real account is the point.

Run with the API's dependencies available, e.g.:
    cd backend && DATABASE_URL=... uv run python scripts/seed_demo.py you@example.com
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.db import async_session_factory
from app.models import Project, User
from app.seed.examox import build_examox


async def _resolve_owner(session, email: str | None) -> User | None:
    """The account the seeded product will belong to.

    Falling back to the earliest account rather than refusing outright
    keeps the zero-argument call working for a solo dev machine (where
    there is usually exactly one account), while still printing WHICH
    account it chose -- silently picking an owner is how you end up
    hunting for a demo project that seeded fine and belongs to someone
    else.
    """
    if email is not None:
        owner = await session.scalar(select(User).where(User.email == email))
        if owner is None:
            print(f"No account found for {email!r}. Register it in the app first.")
        return owner

    owner = await session.scalar(select(User).order_by(User.created_at).limit(1))
    if owner is None:
        print(
            "No accounts exist yet -- register one in the app (or via "
            "POST /auth/register), then re-run with that email."
        )
        return None

    print(f"No owner given; attaching the demo to the earliest account ({owner.email}).")
    return owner


async def main(email: str | None) -> None:
    async with async_session_factory() as session:
        owner = await _resolve_owner(session, email)
        if owner is None:
            return

        existing = await session.scalar(select(Project).where(Project.name == "EXAMOX renewal"))
        if existing is not None:
            print(f"EXAMOX renewal already seeded (project {existing.id}); skipping.")
            return

        project = build_examox(buggy=True, owner_id=owner.id)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        print(
            f"Seeded demo project {project.id} ({project.name!r}) "
            f"for product {project.product.brand_name!r}"
        )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
