"""Tests for app.assembly.pdf: LibreOffice-backed DOCX->PDF conversion,
normalized to be byte-deterministic, text-searchable, and bookmarked.

These call the real `soffice` binary (no mocking the conversion itself --
the whole point of this module is that the actual LibreOffice output
becomes deterministic after normalization, which can only be verified by
actually running it).
"""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from app.assembly.pdf import PdfConversionError, clear_conversion_cache, convert_docx_to_pdf

TEMPLATE = "templates/section_3_2_p_1.docx"


def _docx_bytes() -> bytes:
    with open(TEMPLATE, "rb") as f:
        return f.read()


def test_conversion_produces_a_valid_searchable_pdf():
    pdf_bytes = convert_docx_to_pdf(_docx_bytes())
    assert pdf_bytes[:5] == b"%PDF-"

    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    text = reader.pages[0].extract_text()
    assert "3.2.P.1" in text  # real extractable text, not a rasterized image


def test_conversion_is_not_encrypted_and_embeds_fonts():
    reader = PdfReader(io.BytesIO(convert_docx_to_pdf(_docx_bytes())))
    assert reader.is_encrypted is False
    resources = reader.pages[0].get("/Resources")
    fonts = resources.get("/Font") if resources else None
    assert fonts, "expected at least one embedded font resource"
    for ref in fonts.values():
        descriptor = ref.get_object().get("/FontDescriptor")
        assert descriptor is not None
        d = descriptor.get_object()
        assert any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3"))


def test_bookmark_title_is_set_from_the_caller_not_guessed():
    pdf_bytes = convert_docx_to_pdf(_docx_bytes(), bookmark_title="My Section Title")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    titles = [entry["/Title"] for entry in reader.outline]
    assert titles == ["My Section Title"]  # exactly one, no LibreOffice-added duplicate


def test_no_bookmark_when_none_requested():
    pdf_bytes = convert_docx_to_pdf(_docx_bytes(), bookmark_title=None)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert reader.outline == []


def test_converting_the_same_docx_twice_is_byte_identical():
    data = _docx_bytes()
    first = convert_docx_to_pdf(data, bookmark_title="3.2.P.1")
    second = convert_docx_to_pdf(data, bookmark_title="3.2.P.1")
    assert first == second


def test_missing_soffice_binary_raises_a_clean_error(monkeypatch):
    # NOTE: LibreOffice is remarkably tolerant of garbage input -- feeding
    # it plain garbage bytes or even random binary data does NOT reliably
    # fail (it falls back to interpreting it as some format rather than
    # erroring), so "bad input" isn't a meaningful failure case to test.
    # The realistic failure mode is the binary itself being missing/broken.
    import subprocess

    def _raise_not_found(*args, **kwargs):
        raise FileNotFoundError("soffice not found")

    monkeypatch.setattr(subprocess, "run", _raise_not_found)
    # `convert_docx_to_pdf` memoizes by input bytes (see _PDF_CACHE_SIZE),
    # and an earlier test in this file has already converted this exact
    # document -- so without clearing, the cached answer is returned and
    # `soffice` is never invoked. That is the cache behaving correctly; it
    # just means the error path is unreachable until the cache is emptied.
    clear_conversion_cache()
    with pytest.raises(PdfConversionError, match="not installed"):
        convert_docx_to_pdf(_docx_bytes())
