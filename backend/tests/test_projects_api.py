"""Tests: project CRUD, sequence auto-numbering (0000, 0001, ...), and the
P06 readiness placeholder."""

from __future__ import annotations


async def _create_product(auth_client) -> str:
    resp = await auth_client.post(
        "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
    )
    return resp.json()["id"]


async def test_create_project_requires_existing_product(auth_client):
    resp = await auth_client.post(
        "/projects",
        json={"name": "Ghost project", "product_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


async def test_create_and_fetch_project(auth_client):
    product_id = await _create_product(auth_client)
    resp = await auth_client.post(
        "/projects", json={"name": "EXAMOX renewal", "region": "NAFDAC", "product_id": product_id}
    )
    assert resp.status_code == 201
    project = resp.json()
    assert project["product"]["id"] == product_id
    assert project["sequences"] == []

    fetched = await auth_client.get(f"/projects/{project['id']}")
    assert fetched.status_code == 200


async def test_sequence_auto_numbering_ignores_client_number(auth_client):
    product_id = await _create_product(auth_client)
    project = (
        await auth_client.post(
            "/projects", json={"name": "EXAMOX renewal", "product_id": product_id}
        )
    ).json()
    project_id = project["id"]

    first = await auth_client.post(
        f"/projects/{project_id}/sequences", json={"description": "Initial submission"}
    )
    assert first.status_code == 201
    assert first.json()["number"] == "0000"

    second = await auth_client.post(
        f"/projects/{project_id}/sequences", json={"description": "Amendment"}
    )
    assert second.json()["number"] == "0001"

    listing = await auth_client.get(f"/projects/{project_id}/sequences")
    assert [s["number"] for s in listing.json()] == ["0000", "0001"]

    # the project's nested read reflects both sequences too
    fetched = await auth_client.get(f"/projects/{project_id}")
    assert len(fetched.json()["sequences"]) == 2


async def test_readiness_placeholder(auth_client):
    product_id = await _create_product(auth_client)
    project = (
        await auth_client.post(
            "/projects", json={"name": "EXAMOX renewal", "product_id": product_id}
        )
    ).json()

    resp = await auth_client.get(f"/projects/{project['id']}/readiness")
    assert resp.status_code == 200
    assert resp.json() == {"ready": False, "checks": []}


async def test_unauthenticated_sequence_create_is_rejected(client):
    resp = await client.post(
        "/projects/00000000-0000-0000-0000-000000000000/sequences",
        json={"description": "x"},
    )
    assert resp.status_code == 401
