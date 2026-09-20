"""Accepting a real file into the dossier (P18).

This module owns one decision and its consequences: **what happens to a
file that is not already a PDF.**

WHY convert at UPLOAD rather than at assembly, or rejecting non-PDFs
outright:

- The eCTD manifest and `index.xml` publish an MD5 over the bytes that
  actually ship (`app/ectd/checksum.py`, and P07's whole determinism
  argument). If a `.docx` were stored as-is and converted during the build,
  the checksum could only be computed at build time, and the file a user
  sees listed on the section screen would not be the file being
  checksummed. Converting here means the bytes, the size and the MD5 are
  settled at the moment of upload and never change afterwards.
- It also fails at the right time. A conversion that goes wrong is the
  uploader's problem, and they are standing right there when they upload.
  Discovering it during a build -- possibly weeks later, possibly by
  someone else -- turns a five-second fix into an incident.
- Rejecting non-PDFs outright was the third option and it loses on contact
  with reality: a letter of access or a superintendent pharmacist's
  declaration genuinely arrives as a Word document, and telling a
  regulatory affairs officer to go and convert it by hand is asking them to
  do, less reliably, something this codebase already does deterministically
  (LibreOffice, since P07).

What is NOT accepted: images. A scanned JPEG is a real thing people have,
but an eCTD leaf must be a PDF, and silently wrapping an image in a PDF
container would produce a leaf with no extractable text -- which agency
validators flag and reviewers cannot search. Rejecting with a message that
says what to do ("scan to PDF") is more honest than accepting something
that will be rejected further downstream, where the feedback is worse.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.assembly.pdf import convert_docx_to_pdf
from app.core.storage import StorageClient, get_storage_client

PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Accepted upload types -> whether the bytes need converting before they can
# ship. Everything else is refused; see the module docstring for why images
# in particular are refused rather than wrapped.
ACCEPTED_TYPES: dict[str, bool] = {
    PDF_CONTENT_TYPE: False,
    DOCX_CONTENT_TYPE: True,
}

# WHY a size ceiling at all: a BE study report is genuinely large, but an
# unbounded upload is a way to fill the object store by accident (a whole
# scanned batch record) and every byte here is later read into memory to be
# zipped. 64 MB is comfortably above a real study report and far below
# "someone attached the wrong folder".
MAX_UPLOAD_BYTES = 64 * 1024 * 1024

# PDF's magic number. Checked because `content_type` on a multipart upload
# is whatever the client SAYS it is -- a browser guessing from a file
# extension, or anything at all from a script. A file that claims to be a
# PDF and is not would sail into the package and fail an agency validator
# instead of failing here.
_PDF_MAGIC = b"%PDF-"
# A .docx is a zip; this is the local file header every zip starts with.
_ZIP_MAGIC = b"PK\x03\x04"


class UnsupportedDocumentError(ValueError):
    """Raised for a file this platform will not put in a submission."""


@dataclass(frozen=True)
class IngestedDocument:
    """The result of accepting a file: the bytes that will ship, and the
    facts about them that get stored and published."""

    storage_key: str
    md5: str
    size_bytes: int
    content_type: str


def storage_key_for(project_id, instance_key: str) -> str:
    """Where an uploaded leaf's bytes live.

    Built SERVER-SIDE from the project id and the leaf, never from anything
    the client sent -- the same authorization reasoning
    `app/api/routers/artifacts.py` already writes down at length. That
    endpoint permits a download only under `projects/{project_id}/`, so a
    key constructed anywhere else would either be unreachable or, worse,
    reachable by the wrong project.
    """
    return f"projects/{project_id}/documents/{instance_key}.pdf"


def versioned_storage_key_for(project_id, instance_key: str, version_number: int) -> str:
    """Where ONE version's bytes live (P26).

    WHY every version needs its own key rather than all of them sharing the
    canonical one above: under P18 each upload wrote to the same path, so a
    replacement overwrote its predecessor in the bucket. Version rows
    pointing at a key whose bytes had since been replaced would be a
    history that lies -- worse than having none.

    Still under `projects/{project_id}/`, because that prefix is the
    authorization boundary `app/api/routers/artifacts.py` enforces; a key
    outside it would be unreachable or, worse, reachable by another project.
    """
    return f"projects/{project_id}/documents/versions/{instance_key}/v{version_number}.pdf"


def ingest_document(
    *,
    project_id,
    instance_key: str,
    data: bytes,
    content_type: str,
    filename: str,
    storage: StorageClient | None = None,
    storage_key: str | None = None,
) -> IngestedDocument:
    """Validate, convert if necessary, store, and checksum one upload."""
    if not data:
        raise UnsupportedDocumentError(f"{filename!r} is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UnsupportedDocumentError(
            f"{filename!r} is {len(data) // (1024 * 1024)} MB; the limit is "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )

    needs_conversion = _resolve_type(data, content_type, filename)

    shipping_bytes = (
        convert_docx_to_pdf(data, bookmark_title=filename) if needs_conversion else data
    )

    storage = storage or get_storage_client()
    # An explicit key is how the upload route files each version at its own
    # path (P26); the deterministic one remains the default so every other
    # caller -- the seeds, the tests -- is unchanged.
    key = storage_key or storage_key_for(project_id, instance_key)
    storage.put(key, shipping_bytes, PDF_CONTENT_TYPE)

    return IngestedDocument(
        storage_key=key,
        # Over the SHIPPING bytes, always -- this is the number the eCTD
        # backbone publishes, and it must describe the file in the package
        # rather than the file that was handed to us.
        md5=hashlib.md5(shipping_bytes).hexdigest(),
        size_bytes=len(shipping_bytes),
        content_type=PDF_CONTENT_TYPE,
    )


def _resolve_type(data: bytes, content_type: str, filename: str) -> bool:
    """Decide what this file really is, and whether it needs converting.

    Returns True when the bytes must be converted to PDF.

    The declared `content_type` is treated as a hint and the magic number as
    the truth, because only one of the two is a property of the file.
    """
    if data.startswith(_PDF_MAGIC):
        return False
    if data.startswith(_ZIP_MAGIC) and (
        content_type == DOCX_CONTENT_TYPE or filename.lower().endswith(".docx")
    ):
        return True

    raise UnsupportedDocumentError(
        f"{filename!r} is not a PDF or a .docx. An eCTD leaf must be a searchable "
        "PDF -- scan or export to PDF and upload that. (Images are refused on "
        "purpose: a picture of a page has no text for a reviewer to search.)"
    )
