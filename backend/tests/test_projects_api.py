"""Tests: project CRUD, sequence auto-numbering (0000, 0001, ...), and the
P06 readiness placeholder."""

from __future__ import annotations

import pytest


async def _create_product(auth_client) -> str:
    resp = await auth_client.post(
        "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
    )
    return resp.json()["id"]


async def test_create_project_requires_existing_product(auth_client):
    resp = await auth_client.post(
        "/projects",
        json={"name": "Ghost project", "product_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


async def test_create_and_fetch_project(auth_client):
    product_id = await _create_product(auth_client)
    resp = await auth_client.post(
        "/projects", json={"name": "EXAMOX renewal", "region": "NAFDAC", "product_id": product_id}
    )
    assert resp.status_code == 201
    project = resp.json()
    assert project["product"]["id"] == product_id
    assert project["sequences"] == []

    fetched = await auth_client.get(f"/projects/{project['id']}")
    assert fetched.status_code == 200


async def test_sequence_auto_numbering_ignores_client_number(auth_client):
    product_id = await _create_product(auth_client)
    project = (
        await auth_client.post(
            "/projects", json={"name": "EXAMOX renewal", "product_id": product_id}
        )
    ).json()
    project_id = project["id"]

    first = await auth_client.post(
        f"/projects/{project_id}/sequences", json={"description": "Initial submission"}
    )
    assert first.status_code == 201
    assert first.json()["number"] == "0000"

    second = await auth_client.post(
        f"/projects/{project_id}/sequences", json={"description": "Amendment"}
    )
    assert second.json()["number"] == "0001"

    listing = await auth_client.get(f"/projects/{project_id}/sequences")
    assert [s["number"] for s in listing.json()] == ["0000", "0001"]

    # the project's nested read reflects both sequences too
    fetched = await auth_client.get(f"/projects/{project_id}")
    assert len(fetched.json()["sequences"]) == 2


async def test_readiness_reports_real_findings(auth_client):
    """P06 replaced the placeholder with the real rule engine -- a bare
    product with no manufacturer/APIs/certificates on file is genuinely
    not exportable, and the response says why."""
    product_id = await _create_product(auth_client)
    project = (
        await auth_client.post(
            "/projects", json={"name": "EXAMOX renewal", "product_id": product_id}
        )
    ).json()

    resp = await auth_client.get(f"/projects/{project['id']}/readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_exportable"] is False
    assert body["findings"]  # e.g. R06 (no bioequivalence), R13 (no CPP)


async def test_unauthenticated_sequence_create_is_rejected(client):
    resp = await client.post(
        "/projects/00000000-0000-0000-0000-000000000000/sequences",
        json={"description": "x"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# P25: the sequence-numbering race.
#
# `create_sequence` reads max(number) and then inserts -- two statements, so
# two concurrent POSTs can both read 0002 and both try to write 0003. The
# unique constraint on (project_id, number) is the guarantee; the retry loop
# in the endpoint is the recovery. These three tests cover both halves and
# the behaviour a caller actually sees.
# ---------------------------------------------------------------------------


async def _project_for_sequences(auth_client) -> str:
    product_id = await _create_product(auth_client)
    project = (
        await auth_client.post("/projects", json={"name": "EXAMOX", "product_id": product_id})
    ).json()
    return project["id"]


async def test_duplicate_sequence_number_is_refused_by_the_database(session_factory):
    """The guarantee itself, asserted at the level that actually enforces it.

    WHY test the constraint directly and not only through the endpoint: the
    endpoint's retry is written to ASSUME the database refuses the second
    write. If the constraint were ever dropped from the model, the retry
    would silently become a no-op and the race would reopen with every test
    still green. This test fails the moment that happens.
    """
    import uuid as _uuid

    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.models import Applicant, Product, Project, Sequence, User  # noqa: F401

    async with session_factory() as session:
        user = User(email="race@example.com", hashed_password="x")
        session.add(user)
        await session.flush()
        product = Product(brand_name="EXAMOX", generic_name="Amoxicillin", owner_id=user.id)
        session.add(product)
        await session.flush()
        project = Project(name="EXAMOX", product_id=product.id)
        session.add(project)
        await session.flush()

        session.add(Sequence(project_id=project.id, number="0000"))
        await session.flush()
        session.add(Sequence(project_id=project.id, number="0000"))
        with pytest.raises(IntegrityError):
            await session.flush()

    # ...and the same number under a DIFFERENT project is fine: the
    # constraint scopes uniqueness per project, because 0000 is the first
    # transaction of every dossier, not a global id.
    async with session_factory() as session:
        user = User(email="race2@example.com", hashed_password="x")
        session.add(user)
        await session.flush()
        product = Product(brand_name="OTHER", generic_name="Ibuprofen", owner_id=user.id)
        session.add(product)
        await session.flush()
        a = Project(name="A", product_id=product.id)
        b = Project(name="B", product_id=product.id)
        session.add_all([a, b])
        await session.flush()
        session.add_all(
            [Sequence(project_id=a.id, number="0000"), Sequence(project_id=b.id, number="0000")]
        )
        await session.flush()  # no IntegrityError
        assert _uuid.UUID(str(a.id)) != _uuid.UUID(str(b.id))


@pytest.fixture
async def pg_auth_client(pg_session_factory):
    """An authenticated client backed by a real throwaway Postgres.

    WHY not the ordinary `auth_client`: the default test database is
    in-memory SQLite on a StaticPool -- one shared connection (see
    tests/conftest.py). Concurrent requests through it do not run in
    parallel; they corrupt the single connection ("no active connection").
    A race test on that fixture would be testing the fixture, not the code.
    Postgres gives each session its own connection, so the interleaving
    under test is the real one. Skips when Postgres is not reachable.
    """
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_db
    from app.main import app

    async def override_get_db():
        async with pg_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post(
            "/auth/register", json={"email": "race@example.com", "password": "pw12345678"}
        )
        login = await ac.post(
            "/auth/login", data={"username": "race@example.com", "password": "pw12345678"}
        )
        ac.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        yield ac
    app.dependency_overrides.clear()


async def test_concurrent_sequence_creates_never_collide(pg_auth_client):
    """Fire the POSTs together against real Postgres and assert exactly one
    sequence per number -- no duplicates, no gaps, nobody errored.

    This is the test the constraint and the retry exist for: without the
    constraint two of these writers take the same number; without the retry
    the loser gets a 500 instead of the next free number.
    """
    import asyncio

    project_id = await _project_for_sequences(pg_auth_client)

    responses = await asyncio.gather(
        *(
            pg_auth_client.post(f"/projects/{project_id}/sequences", json={"description": f"s{i}"})
            for i in range(5)
        )
    )

    assert [r.status_code for r in responses] == [201] * 5
    numbers = sorted(r.json()["number"] for r in responses)
    assert numbers == ["0000", "0001", "0002", "0003", "0004"], "duplicate or skipped number"

    listing = await pg_auth_client.get(f"/projects/{project_id}/sequences")
    assert sorted(s["number"] for s in listing.json()) == numbers


async def test_sequence_create_retries_when_it_loses_the_race(auth_client, monkeypatch):
    """The recovery half: when the database refuses our number, we re-read
    and take the next free one instead of surfacing a 500.

    Simulated rather than raced, so it is deterministic: the first commit
    that carries a new Sequence raises IntegrityError exactly as a real
    losing writer would, and the endpoint must then succeed on its retry.
    """
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import Sequence

    project_id = await _project_for_sequences(auth_client)

    real_commit = AsyncSession.commit
    attempts = {"n": 0}

    async def flaky_commit(self):
        # Only interfere with the sequence INSERT, not with any other commit
        # the request happens to make.
        if any(isinstance(obj, Sequence) for obj in self.new):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise IntegrityError("simulated duplicate", None, Exception("uq_sequence"))
        return await real_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", flaky_commit)

    resp = await auth_client.post(f"/projects/{project_id}/sequences", json={"description": "x"})

    assert resp.status_code == 201
    assert resp.json()["number"] == "0000"
    assert attempts["n"] == 2, "expected exactly one failed attempt and one successful retry"
