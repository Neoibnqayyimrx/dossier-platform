"""P27: the conversation with the agency.

A registration is not a package, it is an exchange. The dossier goes in and
a deficiency letter comes back with a deadline; missing that deadline can
lapse the application -- the dossier is fine and the registration is lost
on a date. Until this table existed none of that could be represented.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


async def _project(auth_client) -> str:
    product = (
        await auth_client.post(
            "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
        )
    ).json()
    project = (
        await auth_client.post(
            "/projects", json={"name": "EXAMOX NAFDAC", "product_id": product["id"]}
        )
    ).json()
    return project["id"]


def _letter(**overrides) -> dict:
    payload = {
        "direction": "inbound",
        "correspondence_type": "deficiency-letter",
        "subject": "Deficiencies in Module 3 -- response required",
        "received_or_sent_at": datetime.now(timezone.utc).isoformat(),
        "due_date": str(date.today() + timedelta(days=30)),
    }
    payload.update(overrides)
    return payload


async def test_a_deficiency_letter_round_trips(auth_client):
    project_id = await _project(auth_client)

    created = await auth_client.post(f"/projects/{project_id}/correspondence", json=_letter())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["direction"] == "inbound"
    assert body["correspondence_type"] == "deficiency-letter"
    assert body["status"] == "open"
    assert body["is_overdue"] is False

    listed = (await auth_client.get(f"/projects/{project_id}/correspondence")).json()
    assert [item["id"] for item in listed] == [body["id"]]


async def test_correspondence_need_not_belong_to_a_sequence(auth_client):
    """A pre-submission meeting request belongs to the APPLICATION and to
    no transaction. Forcing a sequence would mean inventing one, and an
    invented sequence number is a regulatory identifier that does not
    exist."""
    project_id = await _project(auth_client)

    created = await auth_client.post(
        f"/projects/{project_id}/correspondence",
        json=_letter(
            correspondence_type="query",
            subject="Pre-submission meeting request",
            due_date=None,
        ),
    )
    assert created.status_code == 201, created.text
    assert created.json()["sequence_id"] is None


async def test_correspondence_can_be_tied_to_the_sequence_it_is_about(auth_client):
    project_id = await _project(auth_client)
    sequence = (await auth_client.post(f"/projects/{project_id}/sequences", json={})).json()

    created = await auth_client.post(
        f"/projects/{project_id}/correspondence",
        json=_letter(sequence_id=sequence["id"]),
    )
    assert created.status_code == 201, created.text
    assert created.json()["sequence_id"] == sequence["id"]


async def test_an_overdue_letter_reports_itself_overdue(auth_client):
    """`is_overdue` is derived at read time, never stored: "is this late?"
    is a question about today, and a stored answer goes stale overnight."""
    project_id = await _project(auth_client)

    overdue = await auth_client.post(
        f"/projects/{project_id}/correspondence",
        json=_letter(due_date=str(date.today() - timedelta(days=1))),
    )
    assert overdue.json()["is_overdue"] is True

    # ...and closing it stops it being overdue, because the work was done.
    closed = await auth_client.patch(
        f"/projects/{project_id}/correspondence/{overdue.json()['id']}",
        json={"status": "closed"},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert closed.json()["is_overdue"] is False


async def test_a_letter_with_no_due_date_is_never_overdue(auth_client):
    project_id = await _project(auth_client)
    created = await auth_client.post(
        f"/projects/{project_id}/correspondence",
        json=_letter(correspondence_type="other", due_date=None),
    )
    assert created.json()["is_overdue"] is False


async def test_correspondence_can_be_deleted(auth_client):
    project_id = await _project(auth_client)
    created = (
        await auth_client.post(f"/projects/{project_id}/correspondence", json=_letter())
    ).json()

    deleted = await auth_client.delete(f"/projects/{project_id}/correspondence/{created['id']}")
    assert deleted.status_code == 204
    assert (await auth_client.get(f"/projects/{project_id}/correspondence")).json() == []


async def test_another_users_correspondence_is_invisible(intruder_client, auth_client):
    """Same boundary as every other project-scoped resource: a regulator's
    letter names deficiencies in someone's dossier and is nobody else's
    business."""
    project_id = await _project(auth_client)
    await auth_client.post(f"/projects/{project_id}/correspondence", json=_letter())

    listed = await intruder_client.get(f"/projects/{project_id}/correspondence")
    assert listed.status_code in (403, 404), listed.text

    created = await intruder_client.post(f"/projects/{project_id}/correspondence", json=_letter())
    assert created.status_code in (403, 404), created.text


async def test_an_unknown_correspondence_type_is_refused(auth_client):
    """A controlled vocabulary that accepts anything is a text column."""
    project_id = await _project(auth_client)

    response = await auth_client.post(
        f"/projects/{project_id}/correspondence",
        json=_letter(correspondence_type="strongly-worded-email"),
    )
    assert response.status_code == 422
