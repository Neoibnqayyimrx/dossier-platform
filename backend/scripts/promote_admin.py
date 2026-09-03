"""Promote an existing account to UserRole.ADMIN (P14b).

There is no self-service or API path to admin (see
app/api/routers/auth.py's module docstring) -- every account registers as
a plain user, and app.api.routers.admin can only be reached BY an admin.
The very first admin has to come from somewhere outside the API, and this
is that somewhere: a one-off operator action, not a feature the app
exposes to itself.

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
from app.models.enums import UserRole


async def main(email: str) -> None:
    async with async_session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"No account found for {email!r}.")
            return
        if user.role == UserRole.ADMIN:
            print(f"{email} is already an admin.")
            return

        user.role = UserRole.ADMIN
        await session.commit()
        print(f"{email} is now an admin.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run python scripts/promote_admin.py <email>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
