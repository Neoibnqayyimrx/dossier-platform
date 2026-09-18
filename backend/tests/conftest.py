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
from app.models import Base, User
from app.models.enums import UserRole

TEST_EMAIL = "tester@examox.example"
TEST_PASSWORD = "s3cret-password"


@pytest.fixture(scope="session", autouse=True)
def libreoffice_listener_is_stopped_at_the_end():
    """Start LibreOffice once per SESSION, not once per test.

    The converter is a lazily-built process-wide singleton
    (`app.assembly.converter.get_converter`), so the first test that
    converts anything starts the listener and every later test reuses it --
    which is the entire point of P1a: starting LibreOffice cost ~1.34 s and
    the suite converts hundreds of documents.

    What this fixture actually adds is the teardown. Without it a `soffice`
    process outlives the run, holding its port, and the NEXT run's listener
    either fails to bind or silently talks to the stale one.
    """
    yield
    from app.assembly.converter import reset_converter

    reset_converter()


@pytest.fixture(autouse=True)
def storage_is_always_in_memory(monkeypatch):
    """Pin object storage to the in-memory client for every test.

    WHY this is autouse and not an opt-in: most of the app takes storage as
    an injectable argument (`storage = storage or get_storage_client()`), so
    tests hand it an InMemoryStorageClient directly. The API ROUTERS cannot
    -- app/api/routers/artifacts.py and documents.py call
    `get_storage_client()` with no injection point -- so a router test gets
    whatever `STORAGE_PROVIDER` resolves to. A developer with
    `STORAGE_PROVIDER=s3` in their (gitignored, untracked) .env therefore ran
    the suite against a real MinIO and watched tests fail for reasons that
    had nothing to do with their change.

    Ambient environment must never decide whether a test passes. This makes
    the router tests behave like every other test in the suite rather than
    like the developer's shell.
    """
    from app.core import storage as storage_module

    monkeypatch.setattr(get_settings(), "storage_provider", "memory")
    # The factory is @lru_cache'd, so a client built under the old setting
    # (or by a previous test) would survive the monkeypatch. Clear on the
    # way in AND out: on the way in so this test gets a memory client, on
    # the way out so the next test does not inherit this one's bucket.
    storage_module.get_storage_client.cache_clear()
    yield
    storage_module.get_storage_client.cache_clear()


ADMIN_EMAIL = "admin@examox.example"
ADMIN_PASSWORD = "s3cret-admin-password"
INTRUDER_EMAIL = "someone-else@examox.example"
INTRUDER_PASSWORD = "s3cret-intruder-password"


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
    for tests that only care about exercising protected write endpoints.

    `client.user_id` is stashed here too -- tests that seed a Project
    directly into the DB (bypassing the API) need it to set
    Product.owner_id, or the ownership check makes their own seeded data
    invisible to this same client (see app.seed.attach_owner's WHY).
    """
    register = await client.post(
        "/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    client.user_id = uuid.UUID(register.json()["id"])
    login = await client.post(
        "/auth/login", data={"username": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
async def admin_client(client, session_factory):
    """Like auth_client, but promoted to UserRole.ADMIN directly in the DB
    before logging in -- there is no API path to admin (see
    app/api/routers/auth.py's module docstring and scripts/promote_admin.py),
    so a test needs the same DB-level shortcut that script uses."""
    register = await client.post(
        "/auth/register", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    user_id = uuid.UUID(register.json()["id"])

    async with session_factory() as session:
        user = await session.get(User, user_id)
        user.role = UserRole.ADMIN
        await session.commit()

    login = await client.post(
        "/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    client.user_id = user_id
    return client


@pytest.fixture
async def intruder_client(client, session_factory):
    """A SECOND registered account, on its own client -- the other half of
    every ownership test (see tests/test_ownership.py).

    WHY a separate AsyncClient rather than swapping the token on `client`:
    httpx keeps ONE Authorization header per client, so re-using it would
    mean the victim and the intruder can never be in flight in the same
    test -- and a test that has to log out the owner to check the intruder
    is a test that can't compare the two answers.

    Depends on `client` so the get_db override is installed (and stays
    installed until after this fixture tears down) -- both clients must
    talk to the same in-memory database or the intruder would 404 on
    everything for the wrong reason: an empty schema.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        register = await ac.post(
            "/auth/register", json={"email": INTRUDER_EMAIL, "password": INTRUDER_PASSWORD}
        )
        ac.user_id = uuid.UUID(register.json()["id"])
        login = await ac.post(
            "/auth/login", data={"username": INTRUDER_EMAIL, "password": INTRUDER_PASSWORD}
        )
        ac.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        yield ac


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
