"""DOCX -> deterministic, bookmarked, searchable PDF conversion (P07).

WHY LibreOffice headless, not a pure-Python library: nothing in the Python
ecosystem converts a real DOCX (styles, tables, embedded images) to PDF
faithfully -- LibreOffice's own rendering engine is what actually lays out
the page. `soffice --headless --convert-to pdf` is the standard way to
drive it from a script/server.

WHY determinism needs a second pass, not just "convert and done": every
`soffice` invocation embeds a wall-clock `/CreationDate` and a
freshly-randomized `/ID` in the PDF trailer. Two conversions of the exact
same input `.docx` therefore produce two *different* files -- which would
break P09's checksums downstream, since a checksum is just a hash of the
raw bytes. Normalizing both fields after conversion is what makes
"same input -> same output" actually true. Verified empirically (converted
the same file twice, confirmed the MD5s differed before normalizing and
matched after) before trusting this, not just assumed.

WHY a fresh LibreOffice profile dir per call
(`-env:UserInstallation=...`): headless LibreOffice locks its user profile
while running; reusing one profile across concurrent/rapid calls is a
well-known source of "soffice already running" failures. A throwaway
profile per call trades a little startup overhead for real isolation.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter

# A fixed, arbitrary placeholder -- never the actual conversion time. Any
# constant works; what matters is that it never varies between runs.
_FIXED_PDF_DATE = "D:20000101000000+00'00'"


class PdfConversionError(RuntimeError):
    """Raised when `soffice` fails to produce a PDF."""


def convert_docx_to_pdf(docx_bytes: bytes, *, bookmark_title: str | None = None) -> bytes:
    """Convert `docx_bytes` to a deterministic PDF via LibreOffice headless.

    `bookmark_title`, if given, becomes the PDF's single top-level bookmark
    -- set directly from the caller's known section title (see
    app.templating.registry.SectionSpec.title) rather than guessed by
    scanning the rendered page for heading-sized text, which would be both
    less reliable and unnecessary when the title is already known data.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        docx_path = tmp_path / "input.docx"
        docx_path.write_bytes(docx_bytes)
        profile_dir = tmp_path / "lo_profile"

        try:
            result = subprocess.run(
                [
                    "soffice",
                    "--headless",
                    "--norestore",
                    f"-env:UserInstallation=file://{profile_dir}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(docx_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError as exc:
            raise PdfConversionError("soffice (LibreOffice) is not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise PdfConversionError("soffice conversion timed out") from exc

        pdf_path = tmp_path / "input.pdf"
        if result.returncode != 0 or not pdf_path.exists():
            raise PdfConversionError(
                f"soffice conversion failed (exit {result.returncode}): {result.stderr}"
            )
        raw_pdf = pdf_path.read_bytes()

    return _normalize_pdf(raw_pdf, bookmark_title=bookmark_title)


def _normalize_pdf(raw_pdf: bytes, *, bookmark_title: str | None) -> bytes:
    """Rebuild `raw_pdf` with pinned metadata and a content-derived `/ID`,
    so byte-identical input always yields byte-identical output."""
    reader = PdfReader(io.BytesIO(raw_pdf))
    writer = PdfWriter()
    # import_outline=False: LibreOffice auto-generates its own bookmark
    # from the docx's "Heading" paragraph style, which would otherwise
    # sit alongside the explicit one below as a confusing near-duplicate.
    # The explicit bookmark (from the caller's known section title) is
    # the authoritative one -- it doesn't depend on every template
    # remembering to use a Heading style correctly.
    writer.append(reader, import_outline=False)

    if bookmark_title:
        writer.add_outline_item(bookmark_title, 0)

    writer.add_metadata(
        {
            "/CreationDate": _FIXED_PDF_DATE,
            "/ModDate": _FIXED_PDF_DATE,
            "/Producer": "dossier-platform",
        }
    )
    # WHY recompute rather than keep LibreOffice's own /ID: pypdf derives
    # its replacement from a checksum of the PDF's own (now-normalized)
    # structure -- content-derived, not time-based -- so it comes out
    # identical whenever the rest of the file does too.
    writer._ID = None
    writer.generate_file_identifiers()

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
