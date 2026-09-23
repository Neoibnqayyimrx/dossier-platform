"""Tests for GET /sections and GET /projects/{id}/artifacts (P11c).

The artifact tests are mostly about authorization: `key` is client-
supplied and the storage client will fetch whatever key it's handed, so
the prefix check is the only thing standing between a caller and every
other project's packages.
"""

from __future__ import annotations

import uuid

from app.core.storage import get_storage_client
from app.models import User
from app.seed.examox import build_examox
from app.templating.registry import SECTIONS


async def _seed_project(session_factory, owner_id: uuid.UUID | None = None) -> uuid.UUID:
    async with session_factory() as session:
        owner = await session.get(User, owner_id) if owner_id is not None else None
        project = build_examox(buggy=False, owner=owner)
        session.add(project)
        await session.commit()
        return project.id


# ---- GET /sections ----------------------------------------------------------


async def test_sections_match_the_registry(client):
    """Derived from SECTIONS, so registering a new section shows up in the
    review UI without a frontend edit -- P04's open/closed payoff."""
    response = await client.get("/sections")
    assert response.status_code == 200
    body = response.json()
    assert {s["number"] for s in body} == set(SECTIONS)
    for entry in body:
        assert entry["title"] == SECTIONS[entry["number"]].title
        assert entry["narrative_slots"] == SECTIONS[entry["number"]].narrative_slots


async def test_a_data_only_section_reports_no_narrative_slots(client):
    """1.2.2 (Registration Form) is pure structured data -- the UI must not
    offer to draft prose for it. Renumbered from 1.2 in P24d."""
    response = await client.get("/sections")
    registration_form = next(s for s in response.json() if s["number"] == "1.2.2")
    assert registration_form["narrative_slots"] == []


# ---- GET /projects/{id}/artifacts -------------------------------------------


async def test_download_returns_the_stored_bytes(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id)
    key = f"projects/{project_id}/ctd-package.zip"
    get_storage_client().put(key, b"PK\x03\x04 pretend zip", "application/zip")

    response = await auth_client.get(f"/projects/{project_id}/artifacts", params={"key": key})
    assert response.status_code == 200
    assert response.content == b"PK\x03\x04 pretend zip"
    assert "attachment" in response.headers["content-disposition"]
    assert "ctd-package.zip" in response.headers["content-disposition"]


async def test_cannot_download_another_projects_artifact(auth_client, session_factory):
    """The whole point of the prefix check: a key that isn't scoped to this
    project is refused even though it exists in storage."""
    project_id = await _seed_project(session_factory, auth_client.user_id)
    other_key = f"projects/{uuid.uuid4()}/ctd-package.zip"
    get_storage_client().put(other_key, b"someone else's dossier", "application/zip")

    response = await auth_client.get(f"/projects/{project_id}/artifacts", params={"key": other_key})
    assert response.status_code == 403


async def test_cannot_escape_the_prefix_with_traversal(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id)
    response = await auth_client.get(
        f"/projects/{project_id}/artifacts",
        params={"key": "kb/secret-document.pdf"},
    )
    assert response.status_code == 403


async def test_unbuilt_artifact_404s_rather_than_500s(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id)
    response = await auth_client.get(
        f"/projects/{project_id}/artifacts",
        params={"key": f"projects/{project_id}/never-built.zip"},
    )
    assert response.status_code == 404


async def test_download_requires_authentication(client, session_factory):
    project_id = await _seed_project(session_factory)
    response = await client.get(
        f"/projects/{project_id}/artifacts",
        params={"key": f"projects/{project_id}/ctd-package.zip"},
    )
    assert response.status_code == 401
