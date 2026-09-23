"""Tests for the /kb HTTP endpoints. Ingest is exercised on the shared
SQLite fixture (auth + validation-gate errors don't need pgvector). Search
needs the real `pg_session_factory` from conftest.py, since it compiles to
pgvector's cosine_distance operator (see tests/test_knowledge.py).
"""

from __future__ import annotations

import uuid

from app.api.deps import get_db
from app.main import app
from app.models import User

Q1A_EXCERPT = """\
2.1.7. Storage Conditions
In general, a drug substance should be evaluated under storage conditions
that test its thermal stability and, if applicable, its sensitivity to
moisture.
"""


async def test_ingest_requires_auth(client):
    resp = await client.post(
        "/kb/ingest",
        json={
            "source": "ICH",
            "title": "Q1A(R2)",
            "version": "Step 4, 2003-02-06",
            "license": "ich-harmonised-guideline",
            "text": Q1A_EXCERPT,
        },
    )
    assert resp.status_code == 401


async def test_ingest_is_refused_to_an_organization_admin(auth_client):
    """403, not 404: unlike someone else's project, there is no reason to
    hide that a shared knowledge base exists from a logged-in user who
    simply may not write to it.

    auth_client is its organization's ADMIN (registering makes it one, gap
    Phase 6a) -- which is exactly why that role can no longer gate a GLOBAL
    table: anyone can give it to themselves by signing up. Only the
    super-admin writes here (see require_superadmin)."""
    resp = await auth_client.post(
        "/kb/ingest",
        json={
            "source": "ICH",
            "title": "Q1A(R2)",
            "version": "Step 4, 2003-02-06",
            "license": "ich-harmonised-guideline",
            "text": Q1A_EXCERPT,
        },
    )
    assert resp.status_code == 403


async def test_ingest_success(superadmin_client):
    resp = await superadmin_client.post(
        "/kb/ingest",
        json={
            "source": "ICH",
            "title": "Q1A(R2) Stability Testing",
            "version": "Step 4, 2003-02-06",
            "license": "ich-harmonised-guideline",
            "url": "https://database.ich.org/sites/default/files/Q1A(R2)%20Guideline.pdf",
            "jurisdiction": "ICH",
            "text": Q1A_EXCERPT,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["was_update"] is False
    assert body["chunks_created"] >= 1
    assert body["source"] == "ICH"


async def test_ingest_rejects_pharmacopoeia_source(superadmin_client):
    resp = await superadmin_client.post(
        "/kb/ingest",
        json={
            "source": "USP",
            "title": "USP Monograph: Amoxicillin",
            "version": "2024",
            "license": "public-domain",
            "text": "monograph text",
        },
    )
    assert resp.status_code == 422
    assert "not on the knowledge-base allowlist" in resp.json()["error"]["message"]


async def test_search_round_trip(pg_session_factory):
    """Full HTTP path against a real Postgres, because GET /kb/search
    compiles to pgvector's cosine_distance operator (see test_knowledge.py
    for why that rules out the SQLite fixture used everywhere else)."""
    from httpx import ASGITransport, AsyncClient

    async def override_get_db():
        async with pg_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            register = await ac.post(
                "/auth/register",
                json={"email": "kb-tester@examox.example", "password": "s3cret-password"},
            )
            # Ingest is super-admin-only (see the kb router's docstring), and
            # there is no API path to it -- same DB-level promotion the
            # superadmin_client fixture and scripts/promote_admin.py use.
            async with pg_session_factory() as promoting:
                user = await promoting.get(User, uuid.UUID(register.json()["id"]))
                user.is_superadmin = True
                await promoting.commit()

            login = await ac.post(
                "/auth/login",
                data={"username": "kb-tester@examox.example", "password": "s3cret-password"},
            )
            token = login.json()["access_token"]

            ingest_resp = await ac.post(
                "/kb/ingest",
                json={
                    "source": "ICH",
                    "title": "Q1A(R2) Stability Testing",
                    "version": "Step 4, 2003-02-06",
                    "license": "ich-harmonised-guideline",
                    "jurisdiction": "ICH",
                    "text": Q1A_EXCERPT,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert ingest_resp.status_code == 201

            search_resp = await ac.get(
                "/kb/search", params={"q": "storage conditions for drug stability"}
            )
            assert search_resp.status_code == 200
            results = search_resp.json()
            assert results
            assert results[0]["section_label"] == "2.1.7. Storage Conditions"
            assert results[0]["source"] == "ICH"
    finally:
        app.dependency_overrides.clear()
