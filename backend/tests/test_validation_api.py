"""Tests for the /projects/{id}/readiness and /validation-overrides HTTP
endpoints (P06): reads are open (matches the P02 convention), creating an
override requires auth, and an override actually flips the export gate."""

from __future__ import annotations

import uuid

from app.seed.examox import build_examox


async def _seed_project(session_factory, buggy: bool = True) -> uuid.UUID:
    async with session_factory() as session:
        project = build_examox(buggy=buggy)
        session.add(project)
        await session.commit()
        return project.id


async def test_readiness_reports_real_findings_for_a_buggy_project(client, session_factory):
    project_id = await _seed_project(session_factory, buggy=True)
    resp = await client.get(f"/projects/{project_id}/readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_exportable"] is False
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert {"R01", "R02", "R03"} <= rule_ids


async def test_readiness_is_exportable_for_a_clean_project(client, session_factory):
    project_id = await _seed_project(session_factory, buggy=False)
    resp = await client.get(f"/projects/{project_id}/readiness")
    body = resp.json()
    assert body["is_exportable"] is True
    # INFO reminders still show up -- exportability isn't "zero findings".
    assert any(f["rule_id"] == "R11" for f in body["findings"])


async def test_readiness_missing_project_404s(client):
    resp = await client.get("/projects/00000000-0000-0000-0000-000000000000/readiness")
    assert resp.status_code == 404


async def test_create_override_requires_auth(client, session_factory):
    project_id = await _seed_project(session_factory, buggy=True)
    resp = await client.post(
        f"/projects/{project_id}/validation-overrides",
        json={"rule_id": "R01", "reason": "x"},
    )
    assert resp.status_code == 401


async def test_override_flips_the_export_gate(auth_client, session_factory):
    project_id = await _seed_project(session_factory, buggy=True)

    before = (await auth_client.get(f"/projects/{project_id}/readiness")).json()
    assert before["is_exportable"] is False
    error_rule_ids = {f["rule_id"] for f in before["findings"] if f["severity"] == "ERROR"}
    assert error_rule_ids  # sanity: there really are errors to override

    for rule_id in error_rule_ids:
        resp = await auth_client.post(
            f"/projects/{project_id}/validation-overrides",
            json={"rule_id": rule_id, "reason": "QA reviewed and accepted the risk."},
        )
        assert resp.status_code == 201

    after = (await auth_client.get(f"/projects/{project_id}/readiness")).json()
    assert after["is_exportable"] is True
    assert set(after["overridden_rule_ids"]) == error_rule_ids
    # the findings themselves are still visible -- overriding doesn't erase
    # the record, it just stops it blocking export.
    assert {f["rule_id"] for f in after["findings"]} >= error_rule_ids


async def test_list_overrides_returns_the_logged_reason(auth_client, session_factory):
    project_id = await _seed_project(session_factory, buggy=True)
    await auth_client.post(
        f"/projects/{project_id}/validation-overrides",
        json={"rule_id": "R01", "reason": "Known issue, accepted by QA lead."},
    )

    resp = await auth_client.get(f"/projects/{project_id}/validation-overrides")
    assert resp.status_code == 200
    [row] = resp.json()
    assert row["rule_id"] == "R01"
    assert row["reason"] == "Known issue, accepted by QA lead."
    assert row["created_by_id"]
