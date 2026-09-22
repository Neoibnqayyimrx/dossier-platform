"""gap Phase 5b: GET /projects/{id}/validation-report -- the findings as a PDF.

The report renders; it does not judge. So the tests ask two things of it:
that it says what the JSON endpoints say (the same rule ids, the same
verdict), and that it says what the JSON cannot show at a glance -- which
checks were WAIVED, and the reason a human recorded for each.
"""

from __future__ import annotations

import io
import uuid

from pypdf import PdfReader

from app.models import Region
from app.seed.examox import build_examox


async def _seed(session_factory, owner_id: uuid.UUID, *, buggy: bool, region: Region) -> uuid.UUID:
    async with session_factory() as session:
        project = build_examox(buggy=buggy, owner_id=owner_id)
        project.region = region
        session.add(project)
        await session.commit()
        return project.id


def _text(pdf: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


async def test_the_readiness_report_says_what_the_json_says_and_what_was_waived(
    auth_client, session_factory
):
    project_id = await _seed(session_factory, auth_client.user_id, buggy=True, region=Region.NAFDAC)
    reason = "Dosage form wording is the originator's own, confirmed with the agency."
    waived = await auth_client.post(
        f"/projects/{project_id}/validation-overrides", json={"rule_id": "R02", "reason": reason}
    )
    assert waived.status_code == 201, waived.text

    readiness = (await auth_client.get(f"/projects/{project_id}/readiness")).json()
    response = await auth_client.get(f"/projects/{project_id}/validation-report")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="validation-report-examox.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")

    text = _text(response.content)
    # The same verdict and the same findings the JSON returns...
    assert not readiness["is_exportable"] and "Blocked" in text
    for rule_id in {f["rule_id"] for f in readiness["findings"]}:
        assert rule_id in text, rule_id
    # ...and what the JSON cannot show at a glance: the waiver, with its reason.
    assert "Waived checks" in text
    assert "originator's own" in " ".join(text.split())
    assert "(waived)" in text


async def test_a_clean_project_reads_exportable(auth_client, session_factory):
    """EU, because a clean NAFDAC EXAMOX is (correctly) still blocked by R20
    until its CPP is attached as a real document -- which is its own test,
    elsewhere. The verdict is compared to the JSON's rather than assumed."""
    project_id = await _seed(session_factory, auth_client.user_id, buggy=False, region=Region.EU)
    readiness = (await auth_client.get(f"/projects/{project_id}/readiness")).json()
    text = _text((await auth_client.get(f"/projects/{project_id}/validation-report")).content)
    assert readiness["is_exportable"], readiness["findings"]
    assert "Result: Exportable" in text
    assert "Waived checks" not in text


async def test_a_sequence_report_covers_every_layer_of_that_sequence(auth_client, session_factory):
    project_id = await _seed(session_factory, auth_client.user_id, buggy=False, region=Region.EU)
    sequence = (await auth_client.post(f"/projects/{project_id}/sequences", json={})).json()
    built = await auth_client.post(
        f"/projects/{project_id}/build/ectd", params={"sequence_id": sequence["id"]}
    )
    assert built.status_code == 201, built.text

    response = await auth_client.get(
        f"/projects/{project_id}/validation-report", params={"sequence_id": sequence["id"]}
    )
    assert response.status_code == 200, response.text
    assert "sequence-0000.pdf" in response.headers["content-disposition"]
    text = " ".join(_text(response.content).split())
    assert "eCTD sequence 0000" in text
    # The external-validator layer's honest advisory: no agency validator ran.
    assert "EXT00" in text


async def test_a_sequence_that_was_never_built_has_no_report(auth_client, session_factory):
    project_id = await _seed(session_factory, auth_client.user_id, buggy=False, region=Region.EU)
    sequence = (await auth_client.post(f"/projects/{project_id}/sequences", json={})).json()
    response = await auth_client.get(
        f"/projects/{project_id}/validation-report", params={"sequence_id": sequence["id"]}
    )
    assert response.status_code == 404
    other = await auth_client.get(
        f"/projects/{project_id}/validation-report", params={"sequence_id": str(uuid.uuid4())}
    )
    assert other.status_code == 404


async def test_a_browser_may_read_the_report_s_filename(auth_client, session_factory):
    """Cross-origin, a script sees only CORS-safelisted response headers
    unless the server exposes more. Content-Disposition is not safelisted,
    so without `expose_headers` the UI would save every report under one
    generic name. httpx ignores CORS, so the Origin header is sent by hand."""
    project_id = await _seed(session_factory, auth_client.user_id, buggy=False, region=Region.EU)
    response = await auth_client.get(
        f"/projects/{project_id}/validation-report", headers={"Origin": "http://localhost:3000"}
    )
    exposed = response.headers.get("access-control-expose-headers", "").lower()
    assert "content-disposition" in exposed
