"""Negative tests for the ownership boundary (P14a).

Every other API test proves an owner CAN reach their own data. None of
them proved that anyone else CANNOT: the suite stayed green through P14a
only because the fixtures were re-pointed at the test user, which
exercises the happy path and nothing else. This file is the missing half
-- a second registered account probing every route that touches data it
does not own.

WHY each probe asserts the message and not only the status: 404 is also
what a mistyped URL returns, so a test that checks `== 404` alone passes
just as happily against a route that does not exist -- which is how a
security test rots into decoration. Every probe here additionally asserts
the DOMAIN message ("Project not found"), which only the ownership check
produces, and `test_the_owner_is_never_stopped_by_the_gate` closes the
same hole from the other side by replaying every probe as the owner.

WHY 404 and not 403 throughout: see require_project_owner's docstring --
someone else's project must be indistinguishable from one that was never
created, rather than confirming its existence to a caller who cannot
touch it.

gap Phase 6a moved the boundary from the USER to the ORGANIZATION, and
extended this file rather than loosening it, in two directions:

- Every stranger probe runs TWICE (the `stranger` fixture): as a plain
  account in another organization, and as a platform SUPER-ADMIN in
  another organization. The user's decision was "super-admin, accounts
  only", and this is where "only" is enforced.
- Every probe the owner replays, a COLLEAGUE replays too -- a plain USER
  the owner's admin added to the same organization. Without that mirror,
  an ownership check still comparing user ids would pass every stranger
  test here and quietly keep the platform single-seat.
"""

from __future__ import annotations

import uuid

import pytest

PROJECT_NOT_FOUND = "Project not found"
PRODUCT_NOT_FOUND = "Product not found"
INGREDIENT_NOT_FOUND = "ActiveIngredient not found"
APPLICANT_NOT_FOUND = "Applicant not found"

# Every child collection the product router factory builds. Listing them
# here (rather than probing one and trusting the factory) is the point:
# the factory takes an `owner_via` argument, and a collection added later
# without it is exactly the regression this file exists to catch.
PRODUCT_CHILD_COLLECTIONS = [
    "manufacturers",
    "apis",
    "excipients",
    "packaging",
    "stability",
    "clinical",
    "batch-formula",
    "certificates",
]


async def _seed_victim(auth_client) -> dict:
    """A product, one manufacturer, one active ingredient with a
    specification row, a project and a sequence -- all created through the
    API by the owner, so every id below is real data owned by someone."""
    product = (
        await auth_client.post(
            "/products",
            json={
                "brand_name": "VICTIMOX",
                "generic_name": "Amoxicillin",
                "dosage_form": "hard gelatin capsule",
                "registration_type": "new",
                "country": "Nigeria",
            },
        )
    ).json()

    manufacturer = (
        await auth_client.post(
            f"/products/{product['id']}/manufacturers",
            json={"name": "Exagon Ltd", "role": "finished product", "gmp_status": "certified"},
        )
    ).json()

    ingredient = (
        await auth_client.post(
            f"/products/{product['id']}/apis",
            json={"inn_name": "Amoxicillin", "strength_value": 500, "strength_unit": "mg"},
        )
    ).json()

    specification = (
        await auth_client.post(
            f"/apis/{ingredient['id']}/specification",
            json={
                "test_name": "Assay",
                "method": "HPLC (BP)",
                "acceptance_criterion": "95.0-105.0 %",
            },
        )
    ).json()

    applicant = (
        await auth_client.post(
            "/applicants",
            json={"company_name": "Victim Pharma Ltd", "country": "Nigeria"},
        )
    ).json()

    project = (
        await auth_client.post(
            "/projects",
            json={
                "name": "VICTIMOX new",
                "region": "NAFDAC",
                "product_id": product["id"],
                "applicant_id": applicant["id"],
            },
        )
    ).json()

    declaration = (
        await auth_client.post(
            f"/projects/{project['id']}/declarations",
            json={"declaration_type": "power-of-attorney", "signed": True},
        )
    ).json()

    sequence = (await auth_client.post(f"/projects/{project['id']}/sequences", json={})).json()

    return {
        "applicant_id": applicant["id"],
        "declaration_id": declaration["id"],
        "product_id": product["id"],
        "manufacturer_id": manufacturer["id"],
        "ingredient_id": ingredient["id"],
        "specification_id": specification["id"],
        "project_id": project["id"],
        "sequence_id": sequence["id"],
    }


@pytest.fixture
async def victim(auth_client):
    return await _seed_victim(auth_client)


@pytest.fixture(params=["another-organization", "superadmin-of-another-organization"])
def stranger(request, intruder_client, superadmin_client):
    """Someone outside the victim's organization, in both forms that
    matter (see the module docstring). Both clients are always built --
    choosing between two ready fixtures is simpler and safer than
    resolving an async fixture lazily from inside a parametrized one."""
    if request.param == "another-organization":
        return intruder_client
    return superadmin_client


# Probes whose OWNER-side answer needs real Postgres: narrative generation
# runs a pgvector similarity search (`<=>`), an operator the SQLite fixture
# has no equivalent for. The intruder side still runs here -- the gate is a
# router dependency, so it answers before retrieval is ever reached -- and
# the owner side is covered on real Postgres in test_narrative_api.py.
PG_ONLY_FOR_THE_OWNER = {"POST /projects/{project}/sections/3.2.P.1/narrative/description:generate"}


def _project_probes(victim: dict) -> list[tuple[str, str, dict | None]]:
    """Every route mounted under /projects/{project_id}.

    WHY a random uuid for the narrative id: the ownership gate is a router
    dependency, so it runs BEFORE the handler looks the narrative up --
    a real id would prove nothing extra, and needing one would mean
    running an LLM generation just to build a fixture.
    """
    project = victim["project_id"]
    sequence = victim["sequence_id"]
    narrative = uuid.uuid4()
    narrative_base = f"/projects/{project}/sections/3.2.P.1/narrative/description"
    return [
        ("GET", f"/projects/{project}", None),
        ("PATCH", f"/projects/{project}", {"name": "renamed by an intruder"}),
        ("DELETE", f"/projects/{project}", None),
        ("POST", f"/projects/{project}/sequences", {}),
        ("GET", f"/projects/{project}/sequences", None),
        ("PATCH", f"/projects/{project}/sequences/{sequence}", {"description": "hijacked"}),
        ("GET", f"/projects/{project}/readiness", None),
        # gap Phase 5b: a report is a READ of every finding on the project,
        # in both its forms -- readiness, and one sequence's eCTD validation.
        ("GET", f"/projects/{project}/validation-report", None),
        ("GET", f"/projects/{project}/validation-report?sequence_id={sequence}", None),
        # P18: the upload path is a WRITE into another project's storage
        # prefix, so it is the probe that matters most on this list.
        ("GET", f"/projects/{project}/documents", None),
        ("DELETE", f"/projects/{project}/documents/1.2.7", None),
        (
            "POST",
            f"/projects/{project}/validation-overrides",
            {"rule_id": "R08", "reason": "not my dossier to sign off"},
        ),
        ("GET", f"/projects/{project}/validation-overrides", None),
        ("POST", f"/projects/{project}/build/ctd", None),
        # sequence_id is a required query param on both eCTD routes -- without
        # it the request never reaches the gate, it just 422s on the param.
        ("POST", f"/projects/{project}/build/ectd?sequence_id={sequence}", None),
        ("POST", f"/projects/{project}/validate/ectd?sequence_id={sequence}", None),
        (
            "GET",
            f"/projects/{project}/artifacts?key=projects/{project}/ctd-package.zip",
            None,
        ),
        ("GET", f"{narrative_base}", None),
        ("POST", f"{narrative_base}:generate", None),
        ("POST", f"{narrative_base}/{narrative}:approve", None),
        ("POST", f"{narrative_base}/{narrative}:edit", {"text": "rewritten by an intruder"}),
    ]


def _ids(probes) -> list[str]:
    return [f"{method} {url.split('?')[0]}" for method, url, _ in probes]


async def _send(client, method: str, url: str, body: dict | None):
    return await client.request(method, url, json=body)


def _assert_looks_unowned(response, expected_message: str) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["error"]["message"] == expected_message, response.text


# ---- project-scoped routes ---------------------------------------------------


@pytest.mark.parametrize(
    "method,url,body",
    # The victim fixture can't be read at collection time, so the ids are
    # baked from a template project and the real ones substituted per test.
    _project_probes({"project_id": "{project}", "sequence_id": "{sequence}"}),
    ids=_ids(_project_probes({"project_id": "{project}", "sequence_id": "{sequence}"})),
)
async def test_a_stranger_cannot_reach_a_project_route(stranger, victim, method, url, body):
    url = url.format(project=victim["project_id"], sequence=victim["sequence_id"])
    _assert_looks_unowned(await _send(stranger, method, url, body), PROJECT_NOT_FOUND)


@pytest.mark.parametrize(
    "method,url,body",
    _project_probes({"project_id": "{project}", "sequence_id": "{sequence}"}),
    ids=_ids(_project_probes({"project_id": "{project}", "sequence_id": "{sequence}"})),
)
async def test_the_owner_is_never_stopped_by_the_gate(
    auth_client, victim, method, url, body, request
):
    """The mirror of the test above, and the reason it isn't vacuous.

    Not `!= 404`: some of these routes legitimately 404 for their owner
    (validating an eCTD sequence that was never built). What must never
    happen is the OWNERSHIP 404 -- the gate mistaking the owner for a
    stranger. That is the exact response asserted against here.
    """
    if request.node.callspec.id in PG_ONLY_FOR_THE_OWNER:
        pytest.skip("owner side needs pgvector; see PG_ONLY_FOR_THE_OWNER")
    url = url.format(project=victim["project_id"], sequence=victim["sequence_id"])
    response = await _send(auth_client, method, url, body)
    if response.status_code == 404:
        assert response.json()["error"]["message"] != PROJECT_NOT_FOUND, response.text


@pytest.mark.parametrize(
    "method,url,body",
    _project_probes({"project_id": "{project}", "sequence_id": "{sequence}"}),
    ids=_ids(_project_probes({"project_id": "{project}", "sequence_id": "{sequence}"})),
)
async def test_a_colleague_is_never_stopped_by_the_gate(
    member_client, victim, method, url, body, request
):
    """gap Phase 6a: the owner's mirror, replayed by a plain USER in the
    same organization. The same assertion as the owner's -- never the
    OWNERSHIP 404 -- because a colleague is supposed to be exactly as able
    to work the dossier as the person who created it."""
    if request.node.callspec.id in PG_ONLY_FOR_THE_OWNER:
        pytest.skip("colleague side needs pgvector; see PG_ONLY_FOR_THE_OWNER")
    url = url.format(project=victim["project_id"], sequence=victim["sequence_id"])
    response = await _send(member_client, method, url, body)
    if response.status_code == 404:
        assert response.json()["error"]["message"] != PROJECT_NOT_FOUND, response.text


async def test_a_colleague_sees_everything_the_organization_holds(member_client, victim):
    """Every listing a stranger sees empty, a colleague sees populated --
    and can write into the product and edit the applicant, the two roots
    the organization now owns."""
    assert [p["id"] for p in (await member_client.get("/projects")).json()] == [
        victim["project_id"]
    ]
    assert [p["id"] for p in (await member_client.get("/products")).json()] == [
        victim["product_id"]
    ]
    assert [a["id"] for a in (await member_client.get("/applicants")).json()] == [
        victim["applicant_id"]
    ]
    added = await member_client.post(
        f"/products/{victim['product_id']}/manufacturers",
        json={"name": "Second site", "role": "finished product", "gmp_status": "certified"},
    )
    assert added.status_code == 201, added.text
    renamed = await member_client.patch(
        f"/applicants/{victim['applicant_id']}", json={"company_name": "Victim Pharma Plc"}
    )
    assert renamed.status_code == 200, renamed.text


async def test_what_a_colleague_creates_the_owner_reaches(member_client, auth_client):
    """The same boundary from the other side: access follows the
    organization, not whoever happened to create the row."""
    product = await member_client.post(
        "/products", json={"brand_name": "COLLEAGUOX", "generic_name": "Ibuprofen"}
    )
    assert product.status_code == 201, product.text
    reached = await auth_client.get(f"/products/{product.json()['id']}")
    assert reached.status_code == 200, reached.text


async def test_a_stranger_sees_none_of_your_projects(stranger, victim):
    listing = await stranger.get("/projects")
    assert listing.status_code == 200
    assert listing.json() == []


# ---- products and their children ---------------------------------------------


@pytest.mark.parametrize(
    "method,body", [("GET", None), ("PATCH", {"country": "Ghana"}), ("DELETE", None)]
)
async def test_a_stranger_cannot_reach_a_product(stranger, victim, method, body):
    response = await _send(stranger, method, f"/products/{victim['product_id']}", body)
    _assert_looks_unowned(response, PRODUCT_NOT_FOUND)


async def test_a_stranger_sees_none_of_your_products(stranger, victim):
    listing = await stranger.get("/products")
    assert listing.status_code == 200
    assert listing.json() == []


@pytest.mark.parametrize("collection", PRODUCT_CHILD_COLLECTIONS)
async def test_a_stranger_cannot_list_a_product_child_collection(stranger, victim, collection):
    response = await stranger.get(f"/products/{victim['product_id']}/{collection}")
    _assert_looks_unowned(response, PRODUCT_NOT_FOUND)


async def test_a_stranger_cannot_write_into_your_product(stranger, victim):
    """A valid payload on purpose: the parent-ownership check lives INSIDE
    the handler, after body validation, so an invalid body would 422 and
    prove nothing about the gate."""
    response = await stranger.post(
        f"/products/{victim['product_id']}/manufacturers",
        json={"name": "Someone else's site", "role": "finished product", "gmp_status": "certified"},
    )
    _assert_looks_unowned(response, PRODUCT_NOT_FOUND)


@pytest.mark.parametrize(
    "method,body", [("GET", None), ("PATCH", {"name": "renamed"}), ("DELETE", None)]
)
async def test_a_stranger_cannot_reach_one_of_your_child_rows(stranger, victim, method, body):
    response = await _send(
        stranger,
        method,
        f"/products/{victim['product_id']}/manufacturers/{victim['manufacturer_id']}",
        body,
    )
    _assert_looks_unowned(response, PRODUCT_NOT_FOUND)


# ---- the one collection that is two hops from an owner -----------------------


async def test_a_stranger_cannot_list_a_drug_substance_specification(stranger, victim):
    """ActiveIngredient has no owner_id of its own; this route is gated by
    the factory's `owner_via="product"` hop (see build_child_router). It is
    the only collection whose ownership is checked through a join, so it
    gets its own probe rather than riding on the loop above."""
    response = await stranger.get(f"/apis/{victim['ingredient_id']}/specification")
    _assert_looks_unowned(response, INGREDIENT_NOT_FOUND)


async def test_a_stranger_cannot_add_a_specification_row(stranger, victim):
    response = await stranger.post(
        f"/apis/{victim['ingredient_id']}/specification",
        json={"test_name": "Assay", "method": "HPLC", "acceptance_criterion": "95-105 %"},
    )
    _assert_looks_unowned(response, INGREDIENT_NOT_FOUND)


@pytest.mark.parametrize(
    "method,body", [("GET", None), ("PATCH", {"acceptance_criterion": "0-1 %"}), ("DELETE", None)]
)
async def test_a_stranger_cannot_reach_a_specification_row(stranger, victim, method, body):
    response = await _send(
        stranger,
        method,
        f"/apis/{victim['ingredient_id']}/specification/{victim['specification_id']}",
        body,
    )
    _assert_looks_unowned(response, INGREDIENT_NOT_FOUND)


# ---- Module 1: an applicant is owned, its declarations are not ---------------


@pytest.mark.parametrize(
    "method,body",
    [("GET", None), ("PATCH", {"company_name": "renamed"}), ("DELETE", None)],
)
async def test_a_stranger_cannot_reach_your_applicant(stranger, victim, method, body):
    """Applicant is the second owned root (P15a) -- it is reached directly
    rather than through a Product, so it carries its own owner_id and its
    router does its own filtering."""
    response = await _send(stranger, method, f"/applicants/{victim['applicant_id']}", body)
    _assert_looks_unowned(response, APPLICANT_NOT_FOUND)


async def test_a_stranger_sees_none_of_your_applicants(stranger, victim):
    listing = await stranger.get("/applicants")
    assert listing.status_code == 200
    assert listing.json() == []


async def test_a_stranger_cannot_name_your_applicant_on_their_own_project(
    stranger, victim, auth_client
):
    """The applicant equivalent of filing against someone else's product:
    the intruder owns the project, so the project-level gate would let this
    through -- only the payload check stops it, and a company's contact
    details would otherwise leak through their own project's reads."""
    their_product = (
        await stranger.post(
            "/products",
            json={"brand_name": "THEIRS", "generic_name": "Testolol", "country": "Nigeria"},
        )
    ).json()

    response = await stranger.post(
        "/projects",
        json={
            "name": "borrowed applicant",
            "region": "NAFDAC",
            "product_id": their_product["id"],
            "applicant_id": victim["applicant_id"],
        },
    )
    _assert_looks_unowned(response, APPLICANT_NOT_FOUND)


async def test_a_stranger_cannot_repoint_their_project_at_your_applicant(stranger, victim):
    """Same hole through PATCH rather than POST -- re-pointable FKs have to
    be re-checked on update, not only at creation."""
    their_product = (
        await stranger.post(
            "/products",
            json={"brand_name": "THEIRS2", "generic_name": "Testolol", "country": "Nigeria"},
        )
    ).json()
    their_project = (
        await stranger.post(
            "/projects",
            json={"name": "theirs", "region": "NAFDAC", "product_id": their_product["id"]},
        )
    ).json()

    response = await stranger.patch(
        f"/projects/{their_project['id']}",
        json={"applicant_id": victim["applicant_id"]},
    )
    _assert_looks_unowned(response, APPLICANT_NOT_FOUND)


async def test_a_stranger_cannot_repoint_their_project_at_your_product(stranger, victim):
    their_product = (
        await stranger.post(
            "/products",
            json={"brand_name": "THEIRS3", "generic_name": "Testolol", "country": "Nigeria"},
        )
    ).json()
    their_project = (
        await stranger.post(
            "/projects",
            json={"name": "theirs", "region": "NAFDAC", "product_id": their_product["id"]},
        )
    ).json()

    response = await stranger.patch(
        f"/projects/{their_project['id']}", json={"product_id": victim["product_id"]}
    )
    _assert_looks_unowned(response, PRODUCT_NOT_FOUND)


# ---- declarations: the first collection whose parent is a Project ------------


async def test_a_stranger_cannot_list_your_declarations(stranger, victim):
    """Parent is Project, not Product, so ownership is reached by the
    factory's owner_via hop (Project -> Product -> owner)."""
    response = await stranger.get(f"/projects/{victim['project_id']}/declarations")
    _assert_looks_unowned(response, PROJECT_NOT_FOUND)


async def test_a_stranger_cannot_add_a_declaration_to_your_project(stranger, victim):
    response = await stranger.post(
        f"/projects/{victim['project_id']}/declarations",
        json={"declaration_type": "declaration-of-authenticity"},
    )
    _assert_looks_unowned(response, PROJECT_NOT_FOUND)


@pytest.mark.parametrize(
    "method,body", [("GET", None), ("PATCH", {"signed": False}), ("DELETE", None)]
)
async def test_a_stranger_cannot_reach_one_of_your_declarations(stranger, victim, method, body):
    response = await _send(
        stranger,
        method,
        f"/projects/{victim['project_id']}/declarations/{victim['declaration_id']}",
        body,
    )
    _assert_looks_unowned(response, PROJECT_NOT_FOUND)


# ---- the hole a project-level check alone would leave ------------------------


async def test_a_stranger_cannot_file_a_project_against_your_product(stranger, victim):
    """The subtlest one. Creating a Project needs only a product_id, and
    without the owner check in create_project the intruder would end up
    owning a project whose whole data tree is someone else's product --
    reachable through every /projects/{id}/... route, since those check
    the project, not the payload that made it."""
    response = await stranger.post(
        "/projects",
        json={"name": "borrowed", "region": "NAFDAC", "product_id": victim["product_id"]},
    )
    _assert_looks_unowned(response, PRODUCT_NOT_FOUND)
