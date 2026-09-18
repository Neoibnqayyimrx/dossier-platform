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

WHY the transport lives in `app.assembly.converter`, not here (P1a): this
module owns the CONTRACT -- a deterministic, bookmarked, searchable PDF --
and that contract must hold however the bytes were produced. Getting
LibreOffice to do the conversion turned out to be where ~97% of the time
went (measured: a 1-paragraph document cost 1341 ms, of which ~1.34 s was
starting LibreOffice), so it became a swappable concern with its own
module. Normalization below applies to every converter's output alike.
"""

from __future__ import annotations

import io
from functools import lru_cache

from pypdf import PdfReader, PdfWriter

from app.assembly.converter import PdfConversionError, get_converter

# A fixed, arbitrary placeholder -- never the actual conversion time. Any
# constant works; what matters is that it never varies between runs.
_FIXED_PDF_DATE = "D:20000101000000+00'00'"


# Re-exported from `converter` so every existing caller and test keeps
# importing it from here, where it has always lived.
__all__ = ["convert_docx_to_pdf", "clear_conversion_cache", "PdfConversionError"]


# WHY caching a subprocess call is SAFE here specifically: this function's
# whole contract (see the module docstring) is that identical input bytes
# produce identical output bytes -- that is what P09's checksums depend on,
# and there is a test asserting a rebuilt package is byte-identical. A cache
# therefore cannot change any result; it can only skip work whose answer is
# already known.
#
# WHY it earns its place: one `soffice` invocation costs about a second, and
# a dossier converts one document per leaf. P17 added fourteen
# not-applicable statements to every NAFDAC package, which made rebuilds --
# and the test suite, which rebuilds constantly -- markedly slower for
# documents that had not changed at all. Bounded so a long-lived server
# cannot grow without limit.
_PDF_CACHE_SIZE = 256


def convert_docx_to_pdf(docx_bytes: bytes, *, bookmark_title: str | None = None) -> bytes:
    """Convert `docx_bytes` to a deterministic PDF via LibreOffice headless.

    `bookmark_title`, if given, becomes the PDF's single top-level bookmark
    -- set directly from the caller's known section title (see
    app.templating.registry.SectionSpec.title) rather than guessed by
    scanning the rendered page for heading-sized text, which would be both
    less reliable and unnecessary when the title is already known data.

    Repeat conversions of identical input are served from a process-local
    cache -- see `_PDF_CACHE_SIZE` above for why that is sound.
    """
    return _convert_docx_to_pdf_cached(docx_bytes, bookmark_title)


def clear_conversion_cache() -> None:
    """Forget every cached conversion.

    Exists for tests that need `soffice` to actually be invoked -- notably
    the one asserting a missing binary raises cleanly. A cached answer for
    identical input is CORRECT there (the bytes are already known, and this
    function's contract is that they cannot differ), but it means the error
    path is never reached, so that test clears the cache first.
    """
    _convert_docx_to_pdf_cached.cache_clear()


@lru_cache(maxsize=_PDF_CACHE_SIZE)
def _convert_docx_to_pdf_cached(docx_bytes: bytes, bookmark_title: str | None) -> bytes:
    raw_pdf = get_converter().convert(docx_bytes)
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
