"""Attach stand-in documents to a seeded project (P18, extended in P22).

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


# The smallest thing that is genuinely a PDF: header, one page WITH A LINE OF
# REAL TEXT ON IT, a real cross-reference table, trailer.
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
#
# WHY THE TEXT WAS ADDED (P22), which is that same trap springing again one
# check later: the page used to be EMPTY, and eCTD check M11 warns when a
# leaf's first page has no extractable text, because that is what a scanned
# image looks like. No fixture had ever tripped it, since the only uploads
# reaching a built package were Module 1 certificates and the eCTD builder is
# EU-only, where Module 1 is not modelled. P22 attaches the CRO's study
# report at 5.3.1.2 -- Module 5, common to every region -- so the blank page
# reached a package for the first time and M11 correctly flagged it.
#
# The fix is the fixture, not the check. M11 is right: a blank page IS what it
# exists to catch, and a stand-in for a real study report should look like a
# document rather than like a scan of nothing. Helvetica is one of the 14
# standard fonts, so it needs no embedding.
def _minimal_pdf() -> bytes:
    stream = (
        b"BT /F1 12 Tf 72 720 Td "
        b"(Stand-in document. Replace with the real signed file.) Tj ET\n"
    )
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>",
        b"<</Length %d>>\nstream\n" % len(stream) + stream + b"endstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
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


# P22: the third-party reports a bioequivalence filing turns on, and the
# leaves they belong at. Neither can be authored here -- a CRO writes both
# -- so a complete fixture has to ATTACH them, exactly as it attaches a
# CPP. 5.3.1.2 is the single most important leaf in a multisource dossier;
# a seeded filing that omitted it would be modelling an incomplete one.
CRO_DOCUMENTS: tuple[tuple[str, str], ...] = (
    ("5.3.1.2", "bioequivalence-study-report.pdf"),
    ("5.3.1.4", "bioanalytical-method-validation-report.pdf"),
)


def attach_certificate_documents(
    project: Project, storage: StorageClient | None = None
) -> list[SectionDocument]:
    """Give every certificate on file -- and the CRO's reports -- a stand-in
    document, so the seeded project is exportable the way a finished filing
    is.

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

    # P22: the CRO's reports, attached only for a filing that actually has a
    # bioequivalence study. A filing taking the biowaiver route owes no
    # study report, and attaching one would put a document in the package
    # contradicting the route the application claims.
    if project.product.bioequivalence_studies:
        for section_number, filename in CRO_DOCUMENTS:
            ingested = ingest_document(
                project_id=project.id,
                instance_key=section_number,
                data=MINIMAL_PDF,
                content_type=PDF_CONTENT_TYPE,
                filename=filename,
                storage=storage,
            )
            created.append(
                SectionDocument(
                    project_id=project.id,
                    section_number=section_number,
                    subject_slug="",
                    storage_key=ingested.storage_key,
                    md5=ingested.md5,
                    size_bytes=ingested.size_bytes,
                    original_filename=filename,
                    content_type=ingested.content_type,
                    uploaded_at=datetime.now(timezone.utc),
                )
            )

    # WHY set_committed_value rather than `project.documents.append(...)`:
    # once the project has been flushed, appending to an unloaded collection
    # makes SQLAlchemy go and SELECT it first -- and under the async engine
    # that emits IO from a plain attribute access, which raises
    # MissingGreenlet rather than merely being slow. This says "the
    # collection is already loaded, and here it is", which is true: nothing
    # else has attached documents to a freshly seeded project.
    set_committed_value(project, "documents", created)
    return created
