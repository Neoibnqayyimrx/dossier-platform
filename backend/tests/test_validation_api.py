"""Tests for the /projects/{id}/readiness and /validation-overrides HTTP
endpoints (P06): every route (reads included) requires the caller to own
the project -- P02's "reads are open" convention no longer holds now that
projects are owned (see app.api.deps.require_project_owner's WHY) -- and
creating an override requires auth on top of that, and an override
actually flips the export gate."""

from __future__ import annotations

import uuid

from app.seed.examox import build_examox


async def _seed_project(
    session_factory, owner_id: uuid.UUID | None = None, buggy: bool = True
) -> uuid.UUID:
    async with session_factory() as session:
        project = build_examox(buggy=buggy, owner_id=owner_id)
        session.add(project)
        await session.commit()
        return project.id


async def test_readiness_reports_real_findings_for_a_buggy_project(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)
    resp = await auth_client.get(f"/projects/{project_id}/readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_exportable"] is False
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert {"R01", "R02", "R03"} <= rule_ids


async def test_readiness_is_exportable_for_a_clean_project(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=False)
    resp = await auth_client.get(f"/projects/{project_id}/readiness")
    body = resp.json()
    assert body["is_exportable"] is True
    # INFO reminders still show up -- exportability isn't "zero findings".
    assert any(f["rule_id"] == "R11" for f in body["findings"])


async def test_readiness_missing_project_404s(auth_client):
    resp = await auth_client.get("/projects/00000000-0000-0000-0000-000000000000/readiness")
    assert resp.status_code == 404


async def test_create_override_requires_auth(client, session_factory):
    project_id = await _seed_project(session_factory, buggy=True)
    resp = await client.post(
        f"/projects/{project_id}/validation-overrides",
        json={"rule_id": "R01", "reason": "x"},
    )
    assert resp.status_code == 401


async def test_override_flips_the_export_gate(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)

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
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)
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


# ---- P15c: a reason with a floor, and a way back ----------------------------


async def test_a_shrug_is_not_a_reason(auth_client, session_factory):
    """The reason is the ENTIRE control on an override -- the platform lets
    a known regulatory error through because a human justified it. A
    free-text field with no floor collects "n/a"."""
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)
    resp = await auth_client.post(
        f"/projects/{project_id}/validation-overrides",
        json={"rule_id": "R01", "reason": "n/a"},
    )
    assert resp.status_code == 422
    assert "reason" in resp.json()["error"]["message"]


async def test_withdrawing_an_override_reinstates_the_block(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)
    before = (await auth_client.get(f"/projects/{project_id}/readiness")).json()
    error_rule_ids = {f["rule_id"] for f in before["findings"] if f["severity"] == "ERROR"}

    created = []
    for rule_id in error_rule_ids:
        resp = await auth_client.post(
            f"/projects/{project_id}/validation-overrides",
            json={"rule_id": rule_id, "reason": "QA reviewed and accepted the risk."},
        )
        created.append(resp.json())
    assert (await auth_client.get(f"/projects/{project_id}/readiness")).json()["is_exportable"]

    withdrawn = await auth_client.post(
        f"/projects/{project_id}/validation-overrides/{created[0]['id']}:withdraw"
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["withdrawn_at"] is not None
    assert withdrawn.json()["withdrawn_by_id"] is not None
    # The original decision survives its own withdrawal -- that is the
    # point of not deleting the row.
    assert withdrawn.json()["reason"] == "QA reviewed and accepted the risk."

    after = (await auth_client.get(f"/projects/{project_id}/readiness")).json()
    assert after["is_exportable"] is False
    assert created[0]["rule_id"] not in after["overridden_rule_ids"]


async def test_withdrawing_twice_is_a_conflict(auth_client, session_factory):
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)
    override = (
        await auth_client.post(
            f"/projects/{project_id}/validation-overrides",
            json={"rule_id": "R01", "reason": "Known issue, accepted by the QA lead."},
        )
    ).json()

    first = await auth_client.post(
        f"/projects/{project_id}/validation-overrides/{override['id']}:withdraw"
    )
    second = await auth_client.post(
        f"/projects/{project_id}/validation-overrides/{override['id']}:withdraw"
    )
    assert first.status_code == 200
    assert second.status_code == 409


async def test_a_withdrawn_override_is_still_listed(auth_client, session_factory):
    """It has to be: a build that happened while it stood is only
    explicable if the record of it survives."""
    project_id = await _seed_project(session_factory, auth_client.user_id, buggy=True)
    override = (
        await auth_client.post(
            f"/projects/{project_id}/validation-overrides",
            json={"rule_id": "R01", "reason": "Known issue, accepted by the QA lead."},
        )
    ).json()
    await auth_client.post(f"/projects/{project_id}/validation-overrides/{override['id']}:withdraw")

    [row] = (await auth_client.get(f"/projects/{project_id}/validation-overrides")).json()
    assert row["id"] == override["id"]
    assert row["withdrawn_at"] is not None
