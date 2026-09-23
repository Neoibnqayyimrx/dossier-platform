"""Tests for the /projects/.../narrative HTTP endpoints.

list/approve/edit are exercised on the shared SQLite fixture (no pgvector
needed -- they operate on an already-created NarrativeGeneration row).
:generate needs the real Postgres (`pg_session_factory`), since it calls
P03's search(), same reason test_kb_api.py's search test does.
"""

from __future__ import annotations

import uuid

from app.models import User
from app.models.narrative import NarrativeGeneration
from app.seed.examox import build_examox


async def _seed_project(session_factory, owner_id: uuid.UUID | None = None) -> uuid.UUID:
    async with session_factory() as session:
        # owner_id is optional here: without one the seed invents its own
        # user and organization, and session.get(User, None) would be a
        # NULL-primary-key lookup (SAWarning) that returns None anyway.
        owner = await session.get(User, owner_id) if owner_id is not None else None
        project = build_examox(buggy=False, owner=owner)
        session.add(project)
        await session.commit()
        return project.id


async def _seed_narrative(session_factory, project_id: uuid.UUID) -> uuid.UUID:
    async with session_factory() as session:
        narrative = NarrativeGeneration(
            project_id=project_id,
            section_number="3.2.P.8.1",
            slot="conclusion",
            model_name="fake-test-model",
            prompt="prompt text",
            output="Draft conclusion text.",
        )
        session.add(narrative)
        await session.commit()
        return narrative.id


async def test_generate_requires_auth(client, session_factory):
    project_id = await _seed_project(session_factory)
    resp = await client.post(
        f"/projects/{project_id}/sections/3.2.P.8.1/narrative/conclusion:generate"
    )
    assert resp.status_code == 401


async def test_list_generations_empty_by_default(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id)
    resp = await auth_client.get(f"/projects/{project_id}/sections/3.2.P.8.1/narrative/conclusion")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_generations_returns_seeded_row(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id)
    await _seed_narrative(session_factory, project_id)
    resp = await auth_client.get(f"/projects/{project_id}/sections/3.2.P.8.1/narrative/conclusion")
    assert resp.status_code == 200
    [row] = resp.json()
    assert row["status"] == "pending"
    assert row["output"] == "Draft conclusion text."


async def test_approve_requires_auth(client, session_factory):
    project_id = await _seed_project(session_factory)
    narrative_id = await _seed_narrative(session_factory, project_id)
    resp = await client.post(
        f"/projects/{project_id}/sections/3.2.P.8.1/narrative/conclusion/{narrative_id}:approve"
    )
    assert resp.status_code == 401


async def test_approve_sets_status_and_final_text(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id)
    narrative_id = await _seed_narrative(session_factory, project_id)

    resp = await auth_client.post(
        f"/projects/{project_id}/sections/3.2.P.8.1/narrative/conclusion/{narrative_id}:approve"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["final_text"] == "Draft conclusion text."


async def test_edit_sets_status_and_overrides_text(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id)
    narrative_id = await _seed_narrative(session_factory, project_id)

    resp = await auth_client.post(
        f"/projects/{project_id}/sections/3.2.P.8.1/narrative/conclusion/{narrative_id}:edit",
        json={"text": "Reviewer-edited text."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "edited"
    assert body["final_text"] == "Reviewer-edited text."


async def test_approve_unknown_narrative_404s(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id)
    resp = await auth_client.post(
        f"/projects/{project_id}/sections/3.2.P.8.1/narrative/conclusion/{uuid.uuid4()}:approve"
    )
    assert resp.status_code == 404


async def test_generate_round_trip_over_http(pg_session_factory):
    """Full HTTP path against real Postgres, mirroring test_kb_api.py's
    test_search_round_trip: POST .../:generate calls P03's search(), which
    compiles to pgvector's cosine_distance. Relies on the ambient
    LLM_PROVIDER=fake (.env / CI) so this never makes a real network call
    -- same convention test_search_round_trip relies on for
    EMBEDDING_PROVIDER."""
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_db
    from app.knowledge.embeddings import FakeEmbeddingClient
    from app.knowledge.ingest import ingest_document
    from app.main import app

    async def override_get_db():
        async with pg_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            register = await ac.post(
                "/auth/register",
                json={
                    "email": "narrative-tester@examox.example",
                    "password": "s3cret-password",
                },
            )
            owner_id = uuid.UUID(register.json()["id"])
            login = await ac.post(
                "/auth/login",
                data={"username": "narrative-tester@examox.example", "password": "s3cret-password"},
            )
            token = login.json()["access_token"]

            async with pg_session_factory() as db:
                project = build_examox(buggy=False, owner=await db.get(User, owner_id))
                db.add(project)
                await db.commit()
                project_id = project.id

                await ingest_document(
                    db,
                    FakeEmbeddingClient(),
                    source="ICH",
                    title="Q1A(R2) Stability Testing",
                    version="Step 4, 2003-02-06",
                    license="ich-harmonised-guideline",
                    text="2.1.6. Stability Testing\nLong term studies establish the stability profile.",
                    chunk_max_chars=500,
                )

            resp = await ac.post(
                f"/projects/{project_id}/sections/3.2.P.8.1/narrative/conclusion:generate",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["narrative"]["status"] == "pending"
            assert "EXAMOX" in body["narrative"]["output"]
    finally:
        app.dependency_overrides.clear()
