"""Tests for /admin/users -- an ORGANIZATION admin's account management
(P14b; scoped to one organization since gap Phase 6a).

Only an org admin reaches it; they see, add and change the accounts of
their own organization; another organization's account behaves as if it
did not exist; and nobody can change their own role or active status here
(the self-lockout guard)."""

from __future__ import annotations

from tests.conftest import (
    INTRUDER_EMAIL,
    MEMBER_EMAIL,
    MEMBER_PASSWORD,
    TEST_EMAIL,
    TEST_PASSWORD,
)


async def test_anonymous_is_rejected(client):
    resp = await client.get("/admin/users")
    assert resp.status_code == 401


async def test_a_plain_member_is_forbidden(member_client):
    resp = await member_client.get("/admin/users")
    assert resp.status_code == 403


async def test_registering_makes_you_the_admin_of_a_new_organization(client):
    """Someone has to be able to add the colleagues, and on a brand-new
    organization there is nobody else."""
    resp = await client.post(
        "/auth/register",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "organization_name": "Examox Pharma Ltd",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "admin"
    assert resp.json()["organization"]["name"] == "Examox Pharma Ltd"
    assert resp.json()["is_superadmin"] is False


async def test_two_registrations_never_share_an_organization(client, auth_client, intruder_client):
    """Self-registration can never land you inside someone else's company
    -- joining one is its admin's decision (POST /admin/users)."""
    theirs = await intruder_client.get("/auth/me")
    assert theirs.json()["organization"]["id"] != str(auth_client.organization_id)


async def test_admin_lists_only_their_own_organization(auth_client, member_client, intruder_client):
    resp = await auth_client.get("/admin/users")
    assert resp.status_code == 200
    rows = {row["email"]: row for row in resp.json()}
    # The colleague is listed; the stranger who registered separately is not.
    assert set(rows) == {TEST_EMAIL, MEMBER_EMAIL}
    assert INTRUDER_EMAIL not in rows
    assert rows[TEST_EMAIL]["role"] == "admin"
    assert rows[MEMBER_EMAIL]["role"] == "user"
    assert {row["organization"]["id"] for row in rows.values()} == {
        str(auth_client.organization_id)
    }


async def test_an_added_member_joins_the_admins_organization(auth_client, member_client):
    me = await member_client.get("/auth/me")
    assert me.json()["organization"]["id"] == str(auth_client.organization_id)
    assert me.json()["role"] == "user"


async def test_adding_a_member_with_a_taken_email_is_a_conflict(auth_client, intruder_client):
    resp = await auth_client.post(
        "/admin/users", json={"email": INTRUDER_EMAIL, "password": MEMBER_PASSWORD}
    )
    assert resp.status_code == 409


async def test_admin_promotes_a_colleague(auth_client, member_client):
    resp = await auth_client.patch(f"/admin/users/{member_client.user_id}", json={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_admin_deactivates_a_colleague(auth_client, member_client):
    resp = await auth_client.patch(
        f"/admin/users/{member_client.user_id}", json={"is_active": False}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # login itself doesn't check is_active...
    login = await member_client.post(
        "/auth/login", data={"username": MEMBER_EMAIL, "password": MEMBER_PASSWORD}
    )
    assert login.status_code == 200
    # ...but get_current_user does.
    member_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    assert (await member_client.get("/products")).status_code == 401


async def test_another_organizations_account_looks_like_it_does_not_exist(
    auth_client, intruder_client
):
    """404, the dossier routes' rule: an org admin cannot deactivate a
    stranger, nor learn by probing that the account exists."""
    resp = await auth_client.patch(
        f"/admin/users/{intruder_client.user_id}", json={"is_active": False}
    )
    assert resp.status_code == 404
    assert (await intruder_client.get("/auth/me")).json()["is_active"] is True


async def test_admin_cannot_change_their_own_role(auth_client):
    resp = await auth_client.patch(f"/admin/users/{auth_client.user_id}", json={"role": "user"})
    assert resp.status_code == 400


async def test_update_unknown_user_404s(auth_client):
    resp = await auth_client.patch(
        "/admin/users/00000000-0000-0000-0000-000000000000", json={"role": "admin"}
    )
    assert resp.status_code == 404


async def test_the_org_admin_role_does_not_reach_the_platform_routes(auth_client):
    """Anyone can make themselves an org admin by registering, so that role
    must buy nothing across organizations."""
    assert (await auth_client.get("/superadmin/users")).status_code == 403
    assert (await auth_client.get("/superadmin/organizations")).status_code == 403
