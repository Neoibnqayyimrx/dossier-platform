"""Tests for GET /enums (P11): the controlled vocabularies the frontend
builds its dropdowns from.

The point of these tests is drift: this endpoint's whole reason to exist
is that the UI must never offer a value the database would reject, so
what matters is that the payload is derived from the enums themselves and
stays complete as they grow.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.enums import DosageForm, GMPStatus, Region


async def _get_enums() -> dict:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/enums")
    assert response.status_code == 200
    return response.json()


async def test_every_dosage_form_is_offered():
    """37 members today, and this must not need editing when a 38th is
    added -- it is derived from the enum, not a copy of it."""
    body = await _get_enums()
    offered = {entry["value"] for entry in body["dosage_form"]}
    assert offered == {member.value for member in DosageForm}


async def test_vocabularies_the_wizard_depends_on_are_present():
    body = await _get_enums()
    for name in (
        "region",
        "registration_type",
        "dosage_form",
        "legal_status",
        "compendial_status",
        "excipient_function",
        "manufacturer_role",
        "gmp_status",
        "packaging_component",
        "stability_study_type",
    ):
        assert body[name], f"{name} vocabulary is empty"


async def test_values_are_exactly_what_the_create_schemas_accept():
    """A dropdown value is POSTed straight back to a Create schema, which
    validates against the enum's `.value` -- so these must match exactly,
    not be prettified for display."""
    body = await _get_enums()
    assert {e["value"] for e in body["region"]} == {m.value for m in Region}
    assert {e["value"] for e in body["gmp_status"]} == {m.value for m in GMPStatus}


async def test_internal_enums_are_not_exposed_as_user_choices():
    """KBSource and NarrativeStatus are internal machinery -- never a
    vocabulary a user picks from."""
    body = await _get_enums()
    assert "kb_source" not in body
    assert "narrative_status" not in body
