"""Tests for POST /projects/{id}/build/ctd (P08): the API surface over
`build_ctd_package` -- a clean project builds and returns a manifest, a
project with unresolved validation errors 409s instead of 500ing, and a
missing project 404s. Mirrors test_validation_api.py's conventions."""

from __future__ import annotations

import uuid

from app.seed.examox import build_examox


async def _seed_project(session_factory, owner_id: uuid.UUID, buggy: bool = False) -> uuid.UUID:
    async with session_factory() as session:
        project = build_examox(buggy=buggy, owner_id=owner_id)
        session.add(project)
        await session.commit()
        return project.id


async def test_build_ctd_returns_a_manifest_for_a_clean_project(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=False)
    resp = await auth_client.post(f"/projects/{project_id}/build/ctd")
    assert resp.status_code == 201
    body = resp.json()
    assert body["storage_key"] == f"projects/{project_id}/ctd-package.zip"
    paths = {f["path"] for f in body["files"]}
    assert "toc.pdf" in paths
    assert "m1/10-cover-letter/1.0.pdf" in paths
    assert all(f["md5"] for f in body["files"])


async def test_build_ctd_409s_when_validation_has_unresolved_errors(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)
    resp = await auth_client.post(f"/projects/{project_id}/build/ctd")
    assert resp.status_code == 409


async def test_build_ctd_missing_project_404s(auth_client):
    resp = await auth_client.post("/projects/00000000-0000-0000-0000-000000000000/build/ctd")
    assert resp.status_code == 404
