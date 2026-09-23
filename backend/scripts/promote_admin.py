"""Make an existing account a platform SUPER-ADMIN (P14b; gap Phase 6a).

There is no self-service or API path to it (see app/api/routers/auth.py's
module docstring) -- app.api.routers.superadmin can only be reached BY a
super-admin, so the very first one has to come from somewhere outside the
API, and this is that somewhere: a one-off operator action, not a feature
the app exposes to itself.

WHY it no longer touches `role`: before gap Phase 6a this script set the
global UserRole.ADMIN. Since 6a the role is WITHIN an organization, and
every registrant is already their own organization's ADMIN -- the thing
only an operator can grant is the platform-wide flag, `is_superadmin`
(accounts across organizations and the shared knowledge base; never
another organization's dossiers).

Run with the API's dependencies available, e.g. (PYTHONPATH=. is required —
every script in this directory needs it, since `app` isn't importable
from inside scripts/ otherwise; see scripts/seed_demo.py):
    cd backend && PYTHONPATH=. uv run python scripts/promote_admin.py someone@example.com
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.db import async_session_factory
from app.models import User


async def main(email: str) -> None:
    async with async_session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"No account found for {email!r}.")
            return
        if user.is_superadmin:
            print(f"{email} is already a super-admin.")
            return

        user.is_superadmin = True
        await session.commit()
        print(f"{email} is now a super-admin.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run python scripts/promote_admin.py <email>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
