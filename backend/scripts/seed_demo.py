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

Run with the API's dependencies available, e.g.:
    cd backend && DATABASE_URL=... uv run python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.db import async_session_factory
from app.models import Project
from app.seed.examox import build_examox


async def main() -> None:
    async with async_session_factory() as session:
        existing = await session.scalar(
            select(Project).where(Project.name == "EXAMOX renewal")
        )
        if existing is not None:
            print(
                f"EXAMOX renewal already seeded (project {existing.id}); skipping."
            )
            return

        project = build_examox(buggy=True)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        print(
            f"Seeded demo project {project.id} ({project.name!r}) "
            f"for product {project.product.brand_name!r}"
        )


if __name__ == "__main__":
    asyncio.run(main())
