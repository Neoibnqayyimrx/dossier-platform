"""P18: the upload path -- real files becoming real leaves.

What these pin down is the difference between a package that is
structurally perfect and one that is submittable. The interesting cases are
all about honesty: a checksum that describes the bytes that ship, a
placeholder that cannot silently reach a regulator, and one project's
documents staying invisible to another.
"""

from __future__ import annotations

import hashlib
import io
import zipfile

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.assembly.assemble import AssemblyBlockedError, assemble_project
from app.core.storage import InMemoryStorageClient
from app.ctd.build import build_ctd_package
from app.documents.ingest import (
    UnsupportedDocumentError,
    ingest_document,
    storage_key_for,
)
from app.models import Base
from app.seed.documents import MINIMAL_PDF, attach_certificate_documents
from app.seed.examox import build_examox
from app.validation.engine import Severity, run_all

CPP_LEAF = "1.2.7"


@pytest.fixture
async def db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _docx_bytes() -> bytes:
    with open("templates/na_statement.docx", "rb") as fh:
        return fh.read()


# ---- ingestion: what may be attached, and what ships ------------------------


def test_a_pdf_is_stored_untouched_and_checksummed_over_the_shipping_bytes():
    storage = InMemoryStorageClient()
    result = ingest_document(
        project_id="p1",
        instance_key=CPP_LEAF,
        data=MINIMAL_PDF,
        content_type="application/pdf",
        filename="CPP_NAFDAC_2026.pdf",
        storage=storage,
    )

    assert storage.get(result.storage_key) == MINIMAL_PDF
    assert result.md5 == hashlib.md5(MINIMAL_PDF).hexdigest()
    assert result.size_bytes == len(MINIMAL_PDF)


def test_a_docx_is_converted_at_upload_so_the_md5_describes_the_pdf():
    """The decision recorded in app/documents/ingest.py, pinned.

    If conversion happened at assembly instead, this md5 would describe a
    .docx that never reaches the package -- and the eCTD backbone publishes
    it as the checksum of the file at the leaf's href.
    """
    storage = InMemoryStorageClient()
    result = ingest_document(
        project_id="p1",
        instance_key="1.2.16",
        data=_docx_bytes(),
        content_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        filename="letter-of-access.docx",
        storage=storage,
    )

    shipped = storage.get(result.storage_key)
    assert shipped.startswith(b"%PDF-")
    assert result.md5 == hashlib.md5(shipped).hexdigest()
    assert result.content_type == "application/pdf"


def test_an_image_is_refused_with_an_instruction():
    """Refused rather than wrapped: an eCTD leaf must be searchable text.

    Wrapping a JPEG in a PDF container would produce something that passes
    for a leaf here and fails at the agency, where the feedback is worse.
    """
    with pytest.raises(UnsupportedDocumentError, match="scan or export to PDF"):
        ingest_document(
            project_id="p1",
            instance_key=CPP_LEAF,
            data=b"\xff\xd8\xff\xe0JFIF-ish bytes",
            content_type="image/jpeg",
            filename="scan.jpg",
            storage=InMemoryStorageClient(),
        )


def test_a_file_that_merely_claims_to_be_a_pdf_is_refused():
    """`content_type` is whatever the client says. The magic number is not."""
    with pytest.raises(UnsupportedDocumentError):
        ingest_document(
            project_id="p1",
            instance_key=CPP_LEAF,
            data=b"this is definitely not a pdf",
            content_type="application/pdf",
            filename="CPP.pdf",
            storage=InMemoryStorageClient(),
        )


def test_the_storage_key_is_derived_from_the_project_never_from_the_client():
    """The authorization boundary artifacts.py relies on.

    Downloads are permitted only under `projects/{id}/`, so a key built
    anywhere else is either unreachable or reachable by the wrong project.
    """
    assert storage_key_for("abc", CPP_LEAF).startswith("projects/abc/")


# ---- the export gate --------------------------------------------------------


def test_R20_blocks_export_while_a_certificate_is_still_a_placeholder():
    project = build_examox(buggy=False)

    report = run_all(project)
    blocking = [f for f in report.errors() if f.rule_id == "R20"]

    assert blocking and blocking[0].section == CPP_LEAF
    assert not report.is_exportable()


def test_R20_goes_quiet_once_the_real_document_is_attached():
    project = build_examox(buggy=False)
    attach_certificate_documents(project, InMemoryStorageClient())

    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R20"]
    assert report.is_exportable()


def test_R20_is_an_error_not_a_warning():
    """Deliberate, and the opposite call to R19's.

    The platform cannot know whether a biowaiver is claimed (R19 warns), but
    it knows for certain that the CPP is a placeholder -- it generated the
    placeholder. A rule certain of a fatal defect should gate.
    """
    findings = [f for f in run_all(build_examox(buggy=False)).findings if f.rule_id == "R20"]
    assert findings and all(f.severity is Severity.ERROR for f in findings)


async def test_assembly_is_refused_while_a_placeholder_stands(db_factory):
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        with pytest.raises(AssemblyBlockedError):
            await assemble_project(db, project, storage=InMemoryStorageClient())


# ---- uploaded documents in the built package --------------------------------


async def test_the_manifest_md5_matches_the_bytes_actually_in_the_zip(db_factory):
    """The claim the whole phase rests on.

    An uploaded PDF is not re-rendered on the way into the package, so the
    md5 recorded at upload must still describe it after it has been placed,
    zipped and shipped. If those ever diverge, every eCTD checksum this
    platform publishes is wrong.
    """
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        result = await build_ctd_package(db, project, storage=storage)

        zip_bytes = storage.get(result.storage_key)

    entry = next(e for e in result.manifest if e.path.endswith(f"{CPP_LEAF}.pdf"))
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        shipped = zf.read(entry.path)

    assert hashlib.md5(shipped).hexdigest() == entry.md5
    assert shipped == MINIMAL_PDF


async def test_an_attached_certificate_replaces_its_placeholder(db_factory):
    """Both would be wrong: a page reading "PLACEHOLDER — REPLACE THIS FILE"
    filed next to the certificate it was standing in for."""
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        result = await build_ctd_package(db, project, storage=storage)

    paths = {entry.path for entry in result.manifest}
    assert "m1/14-certificates/1.2.7.pdf" in paths
    assert not any(p.startswith("m1/14-certificates/cpp-") for p in paths)


async def test_an_uploaded_document_wins_over_a_rendered_section(db_factory):
    """If someone attached the actual signed document, a generated version
    of the same section is not an improvement on it."""
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)

        # 2.3 (Quality Overall Summary) normally renders from a template.
        ingested = ingest_document(
            project_id=project.id,
            instance_key="2.3",
            data=MINIMAL_PDF,
            content_type="application/pdf",
            filename="QOS-signed.pdf",
            storage=storage,
        )
        from datetime import datetime, timezone

        from app.models import SectionDocument

        project.documents.append(
            SectionDocument(
                project_id=project.id,
                section_number="2.3",
                subject_slug="",
                storage_key=ingested.storage_key,
                md5=ingested.md5,
                size_bytes=ingested.size_bytes,
                original_filename="QOS-signed.pdf",
                content_type=ingested.content_type,
                uploaded_at=datetime.now(timezone.utc),
            )
        )

        leaves = await assemble_project(db, project, storage=storage)

    qos = next(leaf for leaf in leaves if leaf.section == "2.3")
    assert qos.md5 == ingested.md5
    assert storage.get(qos.storage_path) == MINIMAL_PDF


async def test_an_uploaded_leaf_with_no_template_still_reaches_the_package(db_factory):
    """5.3.1.2 is a CRO's bioequivalence study report. It has no template and
    never will -- before P18 it was simply absent. The file IS the leaf."""
    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)

        from datetime import datetime, timezone

        from app.models import SectionDocument

        ingested = ingest_document(
            project_id=project.id,
            instance_key="5.3.1.2",
            data=MINIMAL_PDF,
            content_type="application/pdf",
            filename="BE-study-final.pdf",
            storage=storage,
        )
        project.documents.append(
            SectionDocument(
                project_id=project.id,
                section_number="5.3.1.2",
                subject_slug="",
                storage_key=ingested.storage_key,
                md5=ingested.md5,
                size_bytes=ingested.size_bytes,
                original_filename="BE-study-final.pdf",
                content_type=ingested.content_type,
                uploaded_at=datetime.now(timezone.utc),
            )
        )

        result = await build_ctd_package(db, project, storage=storage)

    paths = {entry.path for entry in result.manifest}
    expected = (
        "m5/53-clinical-study-reports/531-biopharmaceutic-studies/"
        "5312-comparative-ba-and-be/5.3.1.2.pdf"
    )
    assert expected in paths


# ---- the coverage check -----------------------------------------------------


def test_an_uploaded_leaf_counts_as_done_only_once_a_file_is_attached():
    """The distinction the per-project mode exists for: a route to attach a
    CPP is a property of the platform; the CPP being in is a property of one
    filing, and reporting the first as the second is the failure P18 removes.
    """
    from scripts.check_target_toc import load_target, producible_keys, resolve_status

    target = load_target()
    producible = producible_keys(target["sections"])
    entry = next(e for e in target["sections"] if e["number"] == CPP_LEAF)

    assert resolve_status(entry, producible) == "placeholder"
    assert resolve_status(entry, producible, {CPP_LEAF}) == "done"


# ---- over HTTP --------------------------------------------------------------


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


async def test_upload_then_list_round_trips(auth_client):
    project_id = await _project(auth_client)

    resp = await auth_client.put(
        f"/projects/{project_id}/documents/{CPP_LEAF}",
        files={"file": ("CPP_NAFDAC_2026.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["original_filename"] == "CPP_NAFDAC_2026.pdf"
    assert body["md5"] == hashlib.md5(MINIMAL_PDF).hexdigest()
    # The key is server-built under the project prefix -- never from the client.
    assert body["storage_key"].startswith(f"projects/{project_id}/")

    listed = (await auth_client.get(f"/projects/{project_id}/documents")).json()
    assert [d["section_number"] for d in listed] == [CPP_LEAF]


async def test_uploading_twice_replaces_rather_than_accumulates(auth_client):
    """One leaf, one document. Two files at one path is a corrupt zip, and
    the model's unique constraint makes that structural rather than hoped-for.
    """
    project_id = await _project(auth_client)
    url = f"/projects/{project_id}/documents/{CPP_LEAF}"

    await auth_client.put(url, files={"file": ("first.pdf", MINIMAL_PDF, "application/pdf")})
    second = await auth_client.put(
        url, files={"file": ("second.pdf", MINIMAL_PDF, "application/pdf")}
    )
    assert second.status_code == 200

    listed = (await auth_client.get(f"/projects/{project_id}/documents")).json()
    assert len(listed) == 1
    assert listed[0]["original_filename"] == "second.pdf"


async def test_an_unplaceable_leaf_is_refused_at_upload_not_at_build(auth_client):
    """2.6 is a Module 2 summary with no declared folder for an upload.

    Accepting it would store bytes, show a green tick, and fail the build
    days later -- the "looks complete, is not" failure this phase removes.
    """
    project_id = await _project(auth_client)
    resp = await auth_client.put(
        f"/projects/{project_id}/documents/9.9.9",
        files={"file": ("x.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert resp.status_code == 404
    assert "target table of contents" in resp.text


async def test_a_bad_file_is_refused_with_a_422_and_an_instruction(auth_client):
    project_id = await _project(auth_client)
    resp = await auth_client.put(
        f"/projects/{project_id}/documents/{CPP_LEAF}",
        files={"file": ("scan.jpg", b"\xff\xd8\xff\xe0nope", "image/jpeg")},
    )
    assert resp.status_code == 422
    assert "scan or export to PDF" in resp.text


async def test_detaching_puts_the_leaf_back_to_a_placeholder(auth_client):
    project_id = await _project(auth_client)
    url = f"/projects/{project_id}/documents/{CPP_LEAF}"
    await auth_client.put(url, files={"file": ("cpp.pdf", MINIMAL_PDF, "application/pdf")})

    assert (await auth_client.delete(url)).status_code == 204
    assert (await auth_client.get(f"/projects/{project_id}/documents")).json() == []


async def test_one_project_cannot_read_anothers_documents(auth_client, intruder_client):
    """The boundary that matters once real regulatory paper is in the bucket.

    A CPP names the applicant, the product and the manufacturing site; a BE
    study report is commercially confidential. `require_project_owner`
    guards the route, and the storage prefix guards the bytes.
    """
    project_id = await _project(auth_client)
    await auth_client.put(
        f"/projects/{project_id}/documents/{CPP_LEAF}",
        files={"file": ("cpp.pdf", MINIMAL_PDF, "application/pdf")},
    )

    listed = (await intruder_client.get(f"/projects/{project_id}/documents")).json()
    assert listed["error"]["message"] == "Project not found"

    uploaded = (await auth_client.get(f"/projects/{project_id}/documents")).json()[0]
    # And not by reaching for the bytes directly either.
    stolen = await intruder_client.get(
        f"/projects/{project_id}/artifacts", params={"key": uploaded["storage_key"]}
    )
    assert stolen.status_code == 404


async def test_a_refused_build_names_the_leaves_not_just_a_409(auth_client):
    """P18 task 9: the ordinary path should be the easier one.

    A build refused because paper is missing is not a malfunction -- it is
    the normal state of a filing in progress. Answering with a paragraph
    makes the user translate prose back into a list of things to go and do;
    answering with the leaves lets the UI link to each one.
    """
    product = await auth_client.post(
        "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
    )
    product_id = product.json()["id"]
    await auth_client.post(
        f"/products/{product_id}/certificates",
        json={"certificate_type": "CPP", "issuing_authority": "NAFDAC"},
    )
    project = await auth_client.post(
        "/projects",
        json={"name": "EXAMOX renewal", "region": "NAFDAC", "product_id": product_id},
    )
    project_id = project.json()["id"]

    resp = await auth_client.post(f"/projects/{project_id}/build/ctd")

    assert resp.status_code == 409
    error = resp.json()["error"]
    assert error["message"]  # the old contract still holds
    blocking = error["blocking"]
    assert blocking, "a refused build must say what refused it"
    assert any(f["rule_id"] == "R20" and f["section"] == CPP_LEAF for f in blocking)


# ---------------------------------------------------------------------------
# P26: version history.
#
# P18 overwrote. The argument for accepting that was that eCTD lifecycle
# versions at the SEQUENCE level -- true, but it only covers what was FILED.
# Between two sequences a leaf can be replaced any number of times, and each
# replacement used to destroy its predecessor's bytes irrecoverably.
# ---------------------------------------------------------------------------


def _pdf_of(marker: bytes) -> bytes:
    """A distinct, still-valid minimal PDF, so two uploads have different
    checksums and we can prove we got the RIGHT one back rather than merely
    a PDF."""
    return MINIMAL_PDF.replace(b"%%EOF", b"% " + marker + b"\n%%EOF")


async def test_replacing_a_document_keeps_the_one_it_replaced(auth_client):
    """The whole point of the phase: the old bytes are still there.

    Not just the old ROW -- the bytes. A history whose entries point at
    storage that has been overwritten is a history that lies, which is
    worse than having none.
    """
    project_id = await _project(auth_client)
    first, second = _pdf_of(b"march-cpp"), _pdf_of(b"april-cpp")

    await auth_client.put(
        f"/projects/{project_id}/documents/{CPP_LEAF}",
        files={"file": ("CPP_March.pdf", first, "application/pdf")},
    )
    await auth_client.put(
        f"/projects/{project_id}/documents/{CPP_LEAF}",
        files={"file": ("CPP_April.pdf", second, "application/pdf")},
    )

    versions = (
        await auth_client.get(f"/projects/{project_id}/documents/{CPP_LEAF}/versions")
    ).json()
    assert [v["version_number"] for v in versions] == [1, 2]
    assert [v["original_filename"] for v in versions] == ["CPP_March.pdf", "CPP_April.pdf"]
    assert [v["is_current"] for v in versions] == [False, True]
    # Different files, so different checksums -- if these matched, the test
    # would be passing on two copies of the same upload.
    assert versions[0]["md5"] != versions[1]["md5"]
    assert versions[0]["storage_key"] != versions[1]["storage_key"]

    superseded = await auth_client.get(
        f"/projects/{project_id}/documents/{CPP_LEAF}/versions/1/content"
    )
    assert superseded.status_code == 200
    assert superseded.content == first, "the replaced bytes were overwritten"
    assert superseded.headers["content-md5"] == hashlib.md5(first).hexdigest()

    current = await auth_client.get(
        f"/projects/{project_id}/documents/{CPP_LEAF}/versions/2/content"
    )
    assert current.content == second


async def test_the_document_row_always_describes_its_newest_version(auth_client):
    """The invariant the denormalisation rests on.

    SectionDocument keeps its own file columns so that assemble.py and the
    lifecycle resolver need no knowledge of versioning. That is only safe
    while those columns equal the newest version row -- otherwise the
    package would ship bytes the history says are superseded.
    """
    project_id = await _project(auth_client)

    for marker in (b"one", b"two", b"three"):
        await auth_client.put(
            f"/projects/{project_id}/documents/{CPP_LEAF}",
            files={"file": (f"CPP_{marker.decode()}.pdf", _pdf_of(marker), "application/pdf")},
        )

    listed = (await auth_client.get(f"/projects/{project_id}/documents")).json()
    document = next(d for d in listed if d["section_number"] == CPP_LEAF)
    versions = (
        await auth_client.get(f"/projects/{project_id}/documents/{CPP_LEAF}/versions")
    ).json()

    newest = versions[-1]
    assert newest["version_number"] == 3
    for field in ("md5", "size_bytes", "storage_key", "original_filename", "content_type"):
        assert document[field] == newest[field], f"{field} drifted from the current version"


async def test_uploading_the_same_file_twice_still_records_a_version(auth_client):
    """An identical re-upload is a real event: someone re-attached the file.

    Recording it is the honest choice -- the checksums being equal is what
    tells a reader nothing actually changed, and that is information the
    history should carry rather than silently discard.
    """
    project_id = await _project(auth_client)
    same = _pdf_of(b"unchanged")

    for _ in range(2):
        await auth_client.put(
            f"/projects/{project_id}/documents/{CPP_LEAF}",
            files={"file": ("CPP.pdf", same, "application/pdf")},
        )

    versions = (
        await auth_client.get(f"/projects/{project_id}/documents/{CPP_LEAF}/versions")
    ).json()
    assert [v["version_number"] for v in versions] == [1, 2]
    assert versions[0]["md5"] == versions[1]["md5"]


async def test_version_history_is_scoped_to_the_owning_project(intruder_client, auth_client):
    """Same boundary as every other document route: someone else's history
    must look exactly like a leaf that was never attached."""
    project_id = await _project(auth_client)
    await auth_client.put(
        f"/projects/{project_id}/documents/{CPP_LEAF}",
        files={"file": ("CPP.pdf", MINIMAL_PDF, "application/pdf")},
    )

    listing = await intruder_client.get(f"/projects/{project_id}/documents/{CPP_LEAF}/versions")
    assert listing.status_code in (403, 404)
    bytes_response = await intruder_client.get(
        f"/projects/{project_id}/documents/{CPP_LEAF}/versions/1/content"
    )
    assert bytes_response.status_code in (403, 404)


async def test_asking_for_a_version_that_never_existed_404s(auth_client):
    project_id = await _project(auth_client)
    await auth_client.put(
        f"/projects/{project_id}/documents/{CPP_LEAF}",
        files={"file": ("CPP.pdf", MINIMAL_PDF, "application/pdf")},
    )

    missing = await auth_client.get(
        f"/projects/{project_id}/documents/{CPP_LEAF}/versions/7/content"
    )
    assert missing.status_code == 404
    assert "version 7" in missing.text

    never_attached = await auth_client.get(f"/projects/{project_id}/documents/1.2.8/versions")
    assert never_attached.status_code == 404
