"""Tests: full CRUD round-trip for a product with nested children, via the
real HTTP surface (httpx + pytest-asyncio, per the P02 spec)."""

from __future__ import annotations


async def _create_product(auth_client) -> dict:
    resp = await auth_client.post(
        "/products",
        json={
            "brand_name": "EXAMOX",
            "generic_name": "Amoxicillin",
            "strength_value": 500,
            "strength_unit": "mg",
            "dosage_form": "hard gelatin capsule",
            "registration_type": "renewal",
            "country": "Nigeria",
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def test_create_list_get_product(auth_client):
    product = await _create_product(auth_client)
    assert product["brand_name"] == "EXAMOX"
    assert product["manufacturers"] == []

    listing = await auth_client.get("/products")
    assert any(p["id"] == product["id"] for p in listing.json())

    fetched = await auth_client.get(f"/products/{product['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == product["id"]


async def test_update_product(auth_client):
    product = await _create_product(auth_client)
    resp = await auth_client.patch(f"/products/{product['id']}", json={"strength_value": 250})
    assert resp.status_code == 200
    assert float(resp.json()["strength_value"]) == 250.0


async def test_get_missing_product_is_404(auth_client):
    resp = await auth_client.get("/products/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == 404


async def test_nested_children_round_trip(auth_client):
    product = await _create_product(auth_client)
    product_id = product["id"]

    manufacturer = await auth_client.post(
        f"/products/{product_id}/manufacturers",
        json={"name": "Exagon", "role": "finished product", "country": "Nigeria"},
    )
    assert manufacturer.status_code == 201
    manufacturer_id = manufacturer.json()["id"]

    api = await auth_client.post(
        f"/products/{product_id}/apis",
        json={"inn_name": "Amoxicillin", "salt_form": "Amoxicillin Trihydrate", "salt_factor": 1.148},
    )
    assert api.status_code == 201

    excipient = await auth_client.post(
        f"/products/{product_id}/excipients", json={"name": "Starch", "function": "diluent"}
    )
    assert excipient.status_code == 201

    # nested children show up on the parent product
    fetched = await auth_client.get(f"/products/{product_id}")
    body = fetched.json()
    assert len(body["manufacturers"]) == 1
    assert len(body["apis"]) == 1
    assert len(body["excipients"]) == 1

    # update a child
    updated = await auth_client.patch(
        f"/products/{product_id}/manufacturers/{manufacturer_id}",
        json={"site_address": "Cadastral Zone, Gwagwalada, Abuja"},
    )
    assert updated.status_code == 200
    assert updated.json()["site_address"] == "Cadastral Zone, Gwagwalada, Abuja"

    # delete a child
    deleted = await auth_client.delete(f"/products/{product_id}/manufacturers/{manufacturer_id}")
    assert deleted.status_code == 204

    after_delete = await auth_client.get(f"/products/{product_id}")
    assert after_delete.json()["manufacturers"] == []


async def test_child_of_missing_product_is_404(auth_client):
    resp = await auth_client.post(
        "/products/00000000-0000-0000-0000-000000000000/manufacturers",
        json={"name": "Exagon", "role": "finished product"},
    )
    assert resp.status_code == 404


async def test_delete_product_cascades(auth_client):
    product = await _create_product(auth_client)
    product_id = product["id"]
    await auth_client.post(
        f"/products/{product_id}/manufacturers",
        json={"name": "Exagon", "role": "finished product"},
    )

    resp = await auth_client.delete(f"/products/{product_id}")
    assert resp.status_code == 204

    missing = await auth_client.get(f"/products/{product_id}")
    assert missing.status_code == 404
