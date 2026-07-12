"""Shared API test fixtures: an isolated in-memory DB per test, wired into
the real FastAPI app via `dependency_overrides`, plus an authenticated
client for the write-endpoint tests.

WHY StaticPool: SQLAlchemy's async sqlite driver opens a new file/connection
per pool checkout by default; for `sqlite+aiosqlite://` (in-memory) that
would give every checkout a *different*, empty database. StaticPool pins the
engine to a single underlying connection so the schema created in the
`create_all` step is still there for the actual request.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.main import app
from app.models import Base

TEST_EMAIL = "tester@examox.example"
TEST_PASSWORD = "s3cret-password"


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
async def client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(client):
    """A client with a registered user's bearer token already attached —
    for tests that only care about exercising protected write endpoints."""
    await client.post("/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    login = await client.post(
        "/auth/login", data={"username": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
