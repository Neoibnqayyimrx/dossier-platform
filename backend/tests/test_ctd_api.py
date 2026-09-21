"""Tests for POST /projects/{id}/build/ctd (P08): the API surface over
`build_ctd_package` -- a clean project builds and returns a manifest, a
project with unresolved validation errors 409s instead of 500ing, and a
missing project 404s. Mirrors test_validation_api.py's conventions."""

from __future__ import annotations

import uuid

from app.seed.documents import attach_certificate_documents
from app.seed.examox import build_examox


async def _seed_project(session_factory, owner_id: uuid.UUID, buggy: bool = False) -> uuid.UUID:
    async with session_factory() as session:
        project = build_examox(buggy=buggy, owner_id=owner_id)
        # P18: a finished filing has its certificate documents attached --
        # R20 blocks the export otherwise, and the corrected EXAMOX fixture
        # is meant to model a dossier that is ready to go.
        #
        # No explicit storage client: the API build reads through
        # `get_storage_client()`, which is cached per process, so the seed
        # has to write into that same one rather than a throwaway.
        attach_certificate_documents(project)
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
    assert "m1/10-cover-letter/1-0.pdf" in paths
    assert all(f["md5"] for f in body["files"])


async def test_build_ctd_409s_when_validation_has_unresolved_errors(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)
    resp = await auth_client.post(f"/projects/{project_id}/build/ctd")
    assert resp.status_code == 409


async def test_build_ctd_missing_project_404s(auth_client):
    resp = await auth_client.post("/projects/00000000-0000-0000-0000-000000000000/build/ctd")
    assert resp.status_code == 404


async def test_a_clean_build_reports_no_overrides(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=False)
    resp = await auth_client.post(f"/projects/{project_id}/build/ctd")
    assert resp.json()["overrides"] == []


async def test_a_build_names_the_checks_that_were_waived(auth_client, session_factory):
    """P15c: a package assembled over a waived ERROR looks exactly like one
    that passed cleanly. Until now the override lived only in the database,
    so whoever downloaded the ZIP had no way to know a deterministic check
    had been set aside for it."""
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)
    readiness = (await auth_client.get(f"/projects/{project_id}/readiness")).json()
    error_rule_ids = {f["rule_id"] for f in readiness["findings"] if f["severity"] == "ERROR"}
    for rule_id in error_rule_ids:
        await auth_client.post(
            f"/projects/{project_id}/validation-overrides",
            json={"rule_id": rule_id, "reason": "Accepted by the QA lead for this filing."},
        )

    resp = await auth_client.post(f"/projects/{project_id}/build/ctd")
    assert resp.status_code == 201
    reported = {o["rule_id"] for o in resp.json()["overrides"]}
    assert reported == error_rule_ids
    assert all(o["reason"] for o in resp.json()["overrides"])


async def test_a_withdrawn_override_no_longer_lets_a_build_through(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)
    readiness = (await auth_client.get(f"/projects/{project_id}/readiness")).json()
    error_rule_ids = {f["rule_id"] for f in readiness["findings"] if f["severity"] == "ERROR"}
    overrides = [
        (
            await auth_client.post(
                f"/projects/{project_id}/validation-overrides",
                json={"rule_id": rule_id, "reason": "Accepted by the QA lead for this filing."},
            )
        ).json()
        for rule_id in error_rule_ids
    ]
    assert (await auth_client.post(f"/projects/{project_id}/build/ctd")).status_code == 201

    await auth_client.post(
        f"/projects/{project_id}/validation-overrides/{overrides[0]['id']}:withdraw"
    )
    blocked = await auth_client.post(f"/projects/{project_id}/build/ctd")
    assert blocked.status_code == 409
