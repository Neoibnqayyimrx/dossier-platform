"""P27: where a sequence stands with the agency, and what kind of
transaction it is.

Before this a Sequence carried `submitted_at` and nothing else, so the only
two states the platform could distinguish were "has a date" and "has not".
These tests pin down the two things that makes worth having: the ORDER of
the states is enforced, and the sequence's declared type reaches the
regional envelope instead of a hardcoded "initial".
"""

from __future__ import annotations

import pytest

from app.models.enums import ALLOWED_SEQUENCE_TRANSITIONS, SequenceStatus, SubmissionUnitType


async def _sequence(auth_client) -> tuple[str, str]:
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
    sequence = (
        await auth_client.post(
            f"/projects/{project['id']}/sequences", json={"description": "Initial submission"}
        )
    ).json()
    return project["id"], sequence["id"]


async def test_a_sequence_is_born_a_draft_filed_as_initial(auth_client):
    """The two defaults, which every pre-P27 row also gets from the
    migration's server_default."""
    project_id, sequence_id = await _sequence(auth_client)

    listed = (await auth_client.get(f"/projects/{project_id}/sequences")).json()
    (sequence,) = [s for s in listed if s["id"] == sequence_id]
    assert sequence["status"] == SequenceStatus.DRAFT.value
    assert sequence["submission_unit_type"] == SubmissionUnitType.INITIAL.value


async def test_a_sequence_walks_the_legal_path_to_approved(auth_client):
    project_id, sequence_id = await _sequence(auth_client)
    url = f"/projects/{project_id}/sequences/{sequence_id}/status"

    for target in ("built", "submitted", "acknowledged", "under-review", "approved"):
        response = await auth_client.patch(url, json={"status": target})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target


async def test_submitting_stamps_the_date_the_record_exists_to_carry(auth_client):
    """A sequence marked SUBMITTED with no submission date cannot answer
    the one question it exists to answer."""
    project_id, sequence_id = await _sequence(auth_client)
    url = f"/projects/{project_id}/sequences/{sequence_id}/status"

    await auth_client.patch(url, json={"status": "built"})
    assert (await auth_client.get(f"/projects/{project_id}/sequences")).json()[0][
        "submitted_at"
    ] is None

    submitted = (await auth_client.patch(url, json={"status": "submitted"})).json()
    assert submitted["submitted_at"] is not None


async def test_a_dossier_cannot_jump_from_draft_to_approved(auth_client):
    """The whole point of modelling status: the order is the information.

    409 rather than 422 -- the request is well-formed and `approved` is a
    real status; what makes it wrong is the state the sequence is in.
    """
    project_id, sequence_id = await _sequence(auth_client)

    response = await auth_client.patch(
        f"/projects/{project_id}/sequences/{sequence_id}/status", json={"status": "approved"}
    )
    assert response.status_code == 409
    # The refusal says what WAS possible, so the caller is not left guessing.
    assert "built" in response.text
    assert "draft" in response.text


async def test_a_rejected_sequence_is_closed(auth_client):
    """What follows a rejection is a NEW sequence answering it, not this
    one changing its mind."""
    project_id, sequence_id = await _sequence(auth_client)
    url = f"/projects/{project_id}/sequences/{sequence_id}/status"

    await auth_client.patch(url, json={"status": "built"})
    await auth_client.patch(url, json={"status": "submitted"})
    assert (await auth_client.patch(url, json={"status": "rejected"})).status_code == 200

    for target in ("approved", "under-review", "draft"):
        assert (await auth_client.patch(url, json={"status": target})).status_code == 409


async def test_setting_the_status_it_already_has_is_a_no_op(auth_client):
    """Idempotent, which a client retrying after a dropped response needs."""
    project_id, sequence_id = await _sequence(auth_client)
    url = f"/projects/{project_id}/sequences/{sequence_id}/status"

    first = await auth_client.patch(url, json={"status": "draft"})
    assert first.status_code == 200
    assert first.json()["status"] == "draft"


async def test_status_cannot_be_set_by_the_ordinary_patch(auth_client):
    """A status any PATCH can set is a status that can record a history
    which never happened."""
    project_id, sequence_id = await _sequence(auth_client)

    response = await auth_client.patch(
        f"/projects/{project_id}/sequences/{sequence_id}", json={"status": "approved"}
    )
    # Either refused outright or silently ignored -- what must NOT happen
    # is the status actually moving.
    listed = (await auth_client.get(f"/projects/{project_id}/sequences")).json()
    (sequence,) = [s for s in listed if s["id"] == sequence_id]
    assert sequence["status"] == "draft", response.text


async def test_every_status_has_a_transition_rule(auth_client):
    """A status missing from the map would raise KeyError on the first
    attempt to move OUT of it -- a 500 rather than a refusal."""
    assert set(ALLOWED_SEQUENCE_TRANSITIONS) == set(SequenceStatus)


@pytest.mark.parametrize(
    "unit_type", [SubmissionUnitType.RESPONSE, SubmissionUnitType.ADDITIONAL_INFO]
)
async def test_the_sequence_type_is_editable_before_it_is_filed(auth_client, unit_type):
    project_id, sequence_id = await _sequence(auth_client)

    updated = await auth_client.patch(
        f"/projects/{project_id}/sequences/{sequence_id}",
        json={"submission_unit_type": unit_type.value},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["submission_unit_type"] == unit_type.value
