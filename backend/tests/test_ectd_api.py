"""Tests for POST /projects/{id}/build/ectd (P09): the API surface over
`build_ectd_sequence`. Mirrors test_ctd_api.py's conventions -- a clean EU
project with a created sequence builds and returns a build report, a
project with unresolved validation errors 409s, a missing project or
missing sequence 404s.
"""

from __future__ import annotations

import uuid

from app.models import Region
from app.seed.examox import build_examox


async def _seed_eu_project(session_factory, buggy: bool = False) -> uuid.UUID:
    async with session_factory() as session:
        project = build_examox(buggy=buggy)
        project.region = Region.EU
        session.add(project)
        await session.commit()
        return project.id


async def _create_sequence(client, project_id: uuid.UUID) -> str:
    resp = await client.post(f"/projects/{project_id}/sequences", json={})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_build_ectd_returns_a_build_report_for_a_clean_project(auth_client, session_factory):
    client = auth_client
    project_id = await _seed_eu_project(session_factory, buggy=False)
    sequence_id = await _create_sequence(client, project_id)

    resp = await client.post(
        f"/projects/{project_id}/build/ectd", params={"sequence_id": sequence_id}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["storage_key"] == f"projects/{project_id}/ectd/0000.zip"
    assert body["sequence_number"] == "0000"
    assert set(body["operations"].values()) == {"new"}


async def test_build_ectd_409s_when_validation_has_unresolved_errors(auth_client, session_factory):
    client = auth_client
    project_id = await _seed_eu_project(session_factory, buggy=True)
    sequence_id = await _create_sequence(client, project_id)

    resp = await client.post(
        f"/projects/{project_id}/build/ectd", params={"sequence_id": sequence_id}
    )
    assert resp.status_code == 409


async def test_build_ectd_missing_project_404s(client):
    resp = await client.post(
        "/projects/00000000-0000-0000-0000-000000000000/build/ectd",
        params={"sequence_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


async def test_build_ectd_missing_sequence_404s(client, session_factory):
    project_id = await _seed_eu_project(session_factory, buggy=False)
    resp = await client.post(
        f"/projects/{project_id}/build/ectd", params={"sequence_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404
