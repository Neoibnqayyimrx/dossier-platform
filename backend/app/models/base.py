"""Declarative base: every table gets a UUID primary key and timestamps.

WHY a shared Base: keeps id/created_at/updated_at identical everywhere, so the
rest of the model files stay focused on domain fields only. The `Uuid` type
maps to a native UUID on Postgres and to CHAR(32) on SQLite, so this same code
runs in the real stack (Postgres) and in this runnable slice (SQLite).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Uuid, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    def __init__(self, **kwargs) -> None:
        """Give every object its id at CONSTRUCTION, not at flush (P18).

        `default=uuid.uuid4` above fires when the row is INSERTed, which
        means a freshly built object has `id is None` until something
        commits it. That was harmless while ids were only ever database
        keys. It stopped being harmless once ids became part of OBJECT
        STORAGE PATHS: `projects/{project_id}/documents/...` is computed
        from the id, and computing it from `None` produces a key that looks
        plausible, stores real bytes, and belongs to no project.

        The column default stays as a backstop for rows created by raw SQL
        or a migration. Assigning here just settles the value earlier, which
        is what lets a whole object graph -- and the storage keys derived
        from it -- be built before anything touches a database.
        """
        kwargs.setdefault("id", uuid.uuid4())
        # WHY the keyword assignment is replicated here instead of
        # `super().__init__(**kwargs)`: SQLAlchemy installs its own
        # `_declarative_constructor` only on classes that do NOT define
        # `__init__`. Defining one here means the ORM's constructor is never
        # installed, and `super()` reaches `object.__init__`, which rejects
        # keywords outright ("object.__init__() takes exactly one
        # argument"). This is the same assignment the declarative
        # constructor performs, including its check that the name is
        # actually mapped -- without which a typo'd field would be silently
        # set on the instance and silently not saved.
        for name, value in kwargs.items():
            if not hasattr(type(self), name):
                raise TypeError(
                    f"{name!r} is an invalid keyword argument for {type(self).__name__}"
                )
            setattr(self, name, value)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
