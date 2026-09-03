"""Tests for /admin/users (P14b): only an admin can reach it at all, an
admin can list every account and change a role/active status, and an
admin can't change their own via this endpoint (the self-lockout guard)."""

from __future__ import annotations

from tests.conftest import ADMIN_EMAIL, TEST_EMAIL, TEST_PASSWORD


async def test_anonymous_is_rejected(client):
    resp = await client.get("/admin/users")
    assert resp.status_code == 401


async def test_ordinary_user_is_forbidden(auth_client):
    resp = await auth_client.get("/admin/users")
    assert resp.status_code == 403


async def test_admin_lists_every_account(admin_client, client):
    await client.post("/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})

    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    emails = {row["email"] for row in resp.json()}
    assert emails == {ADMIN_EMAIL, TEST_EMAIL}
    admin_row = next(row for row in resp.json() if row["email"] == ADMIN_EMAIL)
    assert admin_row["role"] == "admin"
    other_row = next(row for row in resp.json() if row["email"] == TEST_EMAIL)
    assert other_row["role"] == "user"


async def test_admin_promotes_another_user(admin_client, client):
    register = await client.post(
        "/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    user_id = register.json()["id"]

    resp = await admin_client.patch(f"/admin/users/{user_id}", json={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_admin_deactivates_another_user(admin_client, client):
    register = await client.post(
        "/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    user_id = register.json()["id"]

    resp = await admin_client.patch(f"/admin/users/{user_id}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # a deactivated account can no longer authenticate
    login = await client.post(
        "/auth/login", data={"username": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200  # login itself doesn't check is_active...
    resp = await client.get(
        "/products", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert resp.status_code == 401  # ...but get_current_user does


async def test_admin_cannot_change_their_own_role(admin_client):
    resp = await admin_client.get("/admin/users")
    own_id = next(row for row in resp.json() if row["email"] == ADMIN_EMAIL)["id"]

    resp = await admin_client.patch(f"/admin/users/{own_id}", json={"role": "user"})
    assert resp.status_code == 400


async def test_update_unknown_user_404s(admin_client):
    resp = await admin_client.patch(
        "/admin/users/00000000-0000-0000-0000-000000000000", json={"role": "admin"}
    )
    assert resp.status_code == 404
