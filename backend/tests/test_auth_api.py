"""Tests: registration, login, and that write endpoints reject requests
with no (or a bad) bearer token."""

from __future__ import annotations

from tests.conftest import TEST_EMAIL, TEST_PASSWORD


async def test_register_then_login_issues_a_working_token(client):
    register = await client.post(
        "/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert register.status_code == 201
    assert register.json()["email"] == TEST_EMAIL
    assert "hashed_password" not in register.json()  # never leak the hash

    login = await client.post(
        "/auth/login", data={"username": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200
    body = login.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_duplicate_registration_is_a_conflict(client):
    payload = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
    await client.post("/auth/register", json=payload)
    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == 409


async def test_login_wrong_password_is_rejected(client):
    await client.post("/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    resp = await client.post(
        "/auth/login", data={"username": TEST_EMAIL, "password": "wrong-password"}
    )
    assert resp.status_code == 401


async def test_unauthenticated_write_is_rejected(client):
    resp = await client.post(
        "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
    )
    assert resp.status_code == 401


async def test_authenticated_write_succeeds(auth_client):
    resp = await auth_client.post(
        "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
    )
    assert resp.status_code == 201


async def test_reads_do_not_require_auth(client):
    resp = await client.get("/products")
    assert resp.status_code == 200
