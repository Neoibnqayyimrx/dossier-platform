"""Attach stand-in documents to a seeded project (P18).

WHY the fixtures needed this the moment R20 existed: every seed models a
COMPLETE filing -- that is what makes them useful for testing assembly, the
CTD build and the eCTD backbone. R20 blocks export while any certificate on
file is still a placeholder, so a fixture with a CPP row and no CPP document
stopped being a complete filing and became a blocked one. Attaching the
documents is the fix; teaching the tests to override R20 would have been
the same fixture with the new rule switched off.

WHY this goes through `ingest_document` rather than writing rows directly:
it is the path a real upload takes, so the seeds exercise the validation,
conversion and checksum logic instead of quietly bypassing it. A fixture
that takes a shortcut past the code under test is a fixture that stops
telling you the truth.

WHY it is a separate function rather than part of `build_examox`: attaching
a document writes BYTES, so it needs a storage client, and the seed builders
are deliberately pure -- they construct model objects and touch nothing else,
which is why they can be called in tests that have no storage at all.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm.attributes import set_committed_value

from app.core.storage import StorageClient, get_storage_client
from app.ctd.region_profiles import REGION_PROFILES
from app.documents.ingest import PDF_CONTENT_TYPE, ingest_document
from app.models.project import Project
from app.models.section_document import SectionDocument


# The smallest thing that is genuinely a PDF: header, one empty page, a real
# cross-reference table, trailer.
#
# WHY a real (if minimal) PDF rather than b"fake bytes": upload ingestion
# checks the magic number precisely to stop a file that merely CLAIMS to be a
# PDF from reaching a package, and a fixture should not be the one thing
# exempt from the check it exists to exercise.
#
# WHY the xref table is computed rather than omitted: a first version skipped
# it, which was enough for the magic-number check and enough to be zipped --
# and then pypdf could not open it ("startxref not found") the moment a test
# tried to READ an assembled leaf. A fixture that is only valid enough for
# the checks you happened to write is a trap for the next check someone adds.
def _minimal_pdf() -> bytes:
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<<>>>>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"

    # The xref table's whole job is to say where each object starts, so the
    # offsets have to be measured, not guessed -- which is why this is built
    # rather than pasted as a literal.
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    return bytes(out)


MINIMAL_PDF = _minimal_pdf()


def attach_certificate_documents(
    project: Project, storage: StorageClient | None = None
) -> list[SectionDocument]:
    """Give every certificate on file a stand-in document, so the seeded
    project is exportable the way a finished filing is.

    Returns the rows it created, so a caller holding a session can add them.
    """
    storage = storage or get_storage_client()
    profile = REGION_PROFILES.get(project.region)
    if profile is None:
        return []

    held = {certificate.certificate_type for certificate in project.product.certificates}
    created: list[SectionDocument] = []

    for slot in profile.document_slots:
        if slot.certificate_type is None or slot.certificate_type not in held:
            continue

        ingested = ingest_document(
            project_id=project.id,
            instance_key=slot.section_number,
            data=MINIMAL_PDF,
            content_type=PDF_CONTENT_TYPE,
            filename=f"{slot.certificate_type.value}.pdf",
            storage=storage,
        )
        document = SectionDocument(
            project_id=project.id,
            section_number=slot.section_number,
            subject_slug="",
            storage_key=ingested.storage_key,
            md5=ingested.md5,
            size_bytes=ingested.size_bytes,
            original_filename=f"{slot.certificate_type.value}.pdf",
            content_type=ingested.content_type,
            uploaded_at=datetime.now(timezone.utc),
        )
        created.append(document)

    # WHY set_committed_value rather than `project.documents.append(...)`:
    # once the project has been flushed, appending to an unloaded collection
    # makes SQLAlchemy go and SELECT it first -- and under the async engine
    # that emits IO from a plain attribute access, which raises
    # MissingGreenlet rather than merely being slow. This says "the
    # collection is already loaded, and here it is", which is true: nothing
    # else has attached documents to a freshly seeded project.
    set_committed_value(project, "documents", created)
    return created
