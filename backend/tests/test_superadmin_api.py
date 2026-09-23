"""Tests for /superadmin (gap Phase 6a): platform account administration
across organizations -- and, just as deliberately, nothing more.

The user's decision was "super-admin, accounts only". The first half of
this file proves the accounts part works across organizations; the last
test proves the "only": the flag opens no one else's dossier.
"""

from __future__ import annotations

from tests.conftest import INTRUDER_EMAIL, SUPERADMIN_EMAIL, TEST_EMAIL


async def test_a_superadmin_lists_every_organization_with_its_size(
    superadmin_client, auth_client, member_client
):
    resp = await superadmin_client.get("/superadmin/organizations")
    assert resp.status_code == 200, resp.text
    sizes = {row["id"]: row["member_count"] for row in resp.json()}
    # auth_client's organization has two members (it and its colleague);
    # the super-admin's own organization has one.
    assert sizes[str(auth_client.organization_id)] == 2
    assert sorted(sizes.values()) == [1, 2]


async def test_a_superadmin_lists_accounts_across_organizations(
    superadmin_client, auth_client, intruder_client
):
    resp = await superadmin_client.get("/superadmin/users")
    assert resp.status_code == 200
    emails = {row["email"] for row in resp.json()}
    assert emails == {SUPERADMIN_EMAIL, TEST_EMAIL, INTRUDER_EMAIL}
    assert len({row["organization"]["id"] for row in resp.json()}) == 3


async def test_a_new_organization_is_born_with_an_admin_who_can_log_in(superadmin_client):
    created = await superadmin_client.post(
        "/superadmin/organizations",
        json={
            "name": "Lamox Laboratories",
            "admin_email": "ra-lead@lamox.example",
            "admin_password": "first-password",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["member_count"] == 1

    login = await superadmin_client.post(
        "/auth/login", data={"username": "ra-lead@lamox.example", "password": "first-password"}
    )
    me = await superadmin_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert me.json()["organization"]["name"] == "Lamox Laboratories"
    assert me.json()["role"] == "admin"
    assert me.json()["is_superadmin"] is False


async def test_creating_an_organization_with_a_taken_email_creates_nothing(
    superadmin_client, auth_client
):
    """The 409 must not leave an admin-less organization behind."""
    before = len((await superadmin_client.get("/superadmin/organizations")).json())
    resp = await superadmin_client.post(
        "/superadmin/organizations",
        json={"name": "Duplicate Ltd", "admin_email": TEST_EMAIL, "admin_password": "x"},
    )
    assert resp.status_code == 409
    after = len((await superadmin_client.get("/superadmin/organizations")).json())
    assert after == before


async def test_a_superadmin_can_let_a_locked_out_organization_back_in(
    superadmin_client, auth_client
):
    """The case the flag exists for: an organization's only admin was
    deactivated, and nobody inside it can undo that."""
    off = await superadmin_client.patch(
        f"/superadmin/users/{auth_client.user_id}", json={"is_active": False}
    )
    assert off.status_code == 200
    assert (await auth_client.get("/products")).status_code == 401

    on = await superadmin_client.patch(
        f"/superadmin/users/{auth_client.user_id}", json={"is_active": True}
    )
    assert on.status_code == 200
    assert (await auth_client.get("/products")).status_code == 200


async def test_a_superadmin_cannot_lock_themselves_out(superadmin_client):
    resp = await superadmin_client.patch(
        f"/superadmin/users/{superadmin_client.user_id}", json={"is_active": False}
    )
    assert resp.status_code == 400


async def test_the_platform_routes_refuse_a_plain_member(member_client):
    assert (await member_client.get("/superadmin/users")).status_code == 403


async def test_a_superadmin_reads_no_other_organizations_dossier(superadmin_client, auth_client):
    """The "accounts only" half: the flag appears in no ownership check, so another
    organization's product is exactly as invisible to a super-admin as to
    any stranger -- the same 404 and message."""
    product = await auth_client.post(
        "/products", json={"brand_name": "PRIVATOX", "generic_name": "Amoxicillin"}
    )
    product_id = product.json()["id"]

    resp = await superadmin_client.get(f"/products/{product_id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "Product not found"
    assert (await superadmin_client.get("/products")).json() == []
