"""The section list and the conditional answers, over HTTP (P17).

The screen these endpoints back is the first place a filer can see what a
dossier still owes. So the tests are about what a filer would be misled by:
a leaf reported as produced when it is a placeholder, an answer that does
not change the package, and an answer to a question the region profile
never asked.
"""

from __future__ import annotations


async def _project(auth_client) -> str:
    product = await auth_client.post(
        "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
    )
    resp = await auth_client.post(
        "/projects",
        json={
            "name": "EXAMOX renewal",
            "region": "NAFDAC",
            "product_id": product.json()["id"],
        },
    )
    return resp.json()["id"]


async def test_project_defaults_to_the_multisource_scope(auth_client):
    """No client sends `submission_type` yet, and every existing project was
    built assuming this scope -- so the default states what was already true
    rather than leaving the scope unknown."""
    project_id = await _project(auth_client)
    fetched = (await auth_client.get(f"/projects/{project_id}")).json()
    assert fetched["submission_type"] == "multisource-generic"
    assert fetched["condition_answers"] == {}


async def test_section_status_lists_every_target_leaf_with_a_status(auth_client):
    project_id = await _project(auth_client)
    resp = await auth_client.get(f"/projects/{project_id}/section-status")
    assert resp.status_code == 200

    sections = resp.json()
    assert len(sections) == 98
    by_number = {s["number"]: s for s in sections}

    # A declared exclusion: finished, and it says on what basis.
    assert by_number["4.0"]["status"] == "not-applicable"
    assert "multisource" in by_number["4.0"]["citation"]

    # A leaf that renders today.
    assert by_number["3.2.P.1"]["status"] == "produced"

    # A CPP is NOT produced. Something stands in its folder and it is not
    # the certificate the regulator issued -- the distinction this screen
    # exists to keep visible.
    assert by_number["1.2.7"]["status"] == "placeholder"

    # A conditional leaf arrives as a question, unanswered.
    novel_excipients = by_number["3.2.P.4.6"]
    assert novel_excipients["applicability"] == "conditional"
    assert novel_excipients["answer"] is None
    assert novel_excipients["condition"]


async def test_answering_no_turns_a_conditional_leaf_into_a_statement(auth_client):
    project_id = await _project(auth_client)

    resp = await auth_client.patch(
        f"/projects/{project_id}/conditions",
        json={"answers": {"3.2.P.4.6": False}},
    )
    assert resp.status_code == 200
    by_number = {s["number"]: s for s in resp.json()}
    assert by_number["3.2.P.4.6"]["status"] == "not-applicable"
    assert by_number["3.2.P.4.6"]["answer"] is False

    # And it survives the round trip -- the answer is on the project, not in
    # the response.
    reread = (await auth_client.get(f"/projects/{project_id}/section-status")).json()
    assert {s["number"]: s["answer"] for s in reread}["3.2.P.4.6"] is False


async def test_answering_yes_leaves_the_section_owed(auth_client):
    project_id = await _project(auth_client)
    resp = await auth_client.patch(
        f"/projects/{project_id}/conditions",
        json={"answers": {"3.2.P.4.6": True}},
    )
    by_number = {s["number"]: s for s in resp.json()}
    assert by_number["3.2.P.4.6"]["status"] != "not-applicable"


async def test_null_retracts_an_answer_rather_than_meaning_no(auth_client):
    """`null` and `false` are different claims and must stay different.

    `false` says "this section does not apply to my filing" and files a
    statement saying so; `null` says "I have not decided", which R19 warns
    about. Collapsing them would let a retraction quietly file a claim.
    """
    project_id = await _project(auth_client)
    await auth_client.patch(
        f"/projects/{project_id}/conditions", json={"answers": {"3.2.P.4.6": False}}
    )
    resp = await auth_client.patch(
        f"/projects/{project_id}/conditions", json={"answers": {"3.2.P.4.6": None}}
    )
    by_number = {s["number"]: s for s in resp.json()}
    assert by_number["3.2.P.4.6"]["answer"] is None
    assert by_number["3.2.P.4.6"]["status"] != "not-applicable"


async def test_answers_to_unasked_questions_are_not_stored(auth_client):
    """Only numbers the region profile declares conditional are accepted.

    An answer to a question nobody asked would sit in the column invisibly
    and could start meaning something the day that number became
    conditional in config.
    """
    project_id = await _project(auth_client)
    await auth_client.patch(
        f"/projects/{project_id}/conditions",
        json={"answers": {"2.3": False, "9.9.9": True}},
    )
    project = (await auth_client.get(f"/projects/{project_id}")).json()
    assert project["condition_answers"] == {}


async def test_switching_submission_type_changes_the_section_list(auth_client):
    project_id = await _project(auth_client)
    await auth_client.patch(
        f"/projects/{project_id}", json={"submission_type": "new-chemical-entity"}
    )

    sections = (await auth_client.get(f"/projects/{project_id}/section-status")).json()
    by_number = {s["number"]: s for s in sections}
    assert by_number["4.0"]["applicability"] == "required"
    assert by_number["4.0"]["status"] != "not-applicable"


async def test_section_status_is_owned(client, auth_client, intruder_client):
    """Same ownership boundary as every other project route (P14a)."""
    project_id = await _project(auth_client)
    resp = await intruder_client.get(f"/projects/{project_id}/section-status")
    assert resp.status_code == 404
