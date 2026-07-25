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

import uuid

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
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


@pytest.fixture
async def pg_session_factory():
    """A throwaway real Postgres database (created and dropped per test),
    for the handful of tests (P03 knowledge-base search) that need actual
    pgvector operators SQLite has no equivalent for. Skips itself if no
    Postgres is reachable, so `pytest -q` still passes without
    `docker compose up -d db` running; CI's pgvector service always
    provides one. Shared by test_knowledge.py and test_kb_api.py.
    """
    base_url = make_url(get_settings().database_url)
    maint_url = base_url.set(drivername="postgresql", database="postgres")
    test_db = f"dossier_test_kb_{uuid.uuid4().hex[:8]}"

    try:
        import psycopg

        with psycopg.connect(
            maint_url.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            conn.execute(f'CREATE DATABASE "{test_db}"')
    except Exception as exc:
        pytest.skip(
            f"Postgres not reachable ({exc}); run `docker compose up -d db` for KB search tests"
        )

    # WHY the URL object, not str(test_url): SQLAlchemy's URL.__str__ masks
    # the password as "***" (it's meant for logging) — create_async_engine
    # accepts a URL object directly, which keeps the real password intact.
    #
    # WHY the try starts here, not after engine setup: a failure while
    # creating the engine/extension/tables (as happened once here, from the
    # str(url) password-masking bug above) must still drop the throwaway
    # database — cleanup has to cover every failure mode after CREATE
    # DATABASE succeeds, not just the happy path.
    test_url = base_url.set(database=test_db)
    engine = None
    try:
        engine = create_async_engine(test_url)
        async with engine.begin() as conn:
            await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, expire_on_commit=False)
        yield factory
    finally:
        if engine is not None:
            await engine.dispose()
        with psycopg.connect(
            maint_url.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{test_db}"')
