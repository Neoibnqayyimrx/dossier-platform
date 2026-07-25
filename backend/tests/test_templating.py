"""Tests: the real docxtpl template engine (P04) renders section .docx files
from the EXAMOX seed data, with data slots correctly filled and narrative
slots left as clearly-marked placeholders when no narrative is supplied."""

from __future__ import annotations

import io
import zipfile

import pytest
from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.storage import InMemoryStorageClient
from app.models import Base
from app.seed.examox import build_examox
from app.templating.registry import get_section
from app.templating.render import render_section


@pytest.fixture
def project():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    project = build_examox(buggy=False)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def _document_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def test_get_section_rejects_unknown_number():
    with pytest.raises(KeyError):
        get_section("9.9.9")


def test_render_cover_letter_fills_data_slots(project):
    storage = InMemoryStorageClient()
    result = render_section("1.0", project, storage=storage)

    assert result.storage_key == f"projects/{project.id}/sections/1.0.docx"
    assert result.size_bytes == len(storage.get(result.storage_key))

    text = _document_text(storage.get(result.storage_key))
    assert "NAFDAC" in text
    assert "EXAMOX" in text
    assert "Exagon" in text
    assert "[[AI DRAFT PENDING" in text  # narrative slot, no narrative supplied
    assert "{{" not in text and "{%" not in text  # no leftover jinja tags


def test_render_p1_fills_composition_table(project):
    storage = InMemoryStorageClient()
    result = render_section("3.2.P.1", project, storage=storage)

    text = _document_text(storage.get(result.storage_key))
    assert "EXAMOX" in text
    assert "500.000 mg" in text
    assert "144.00" in text  # declared batch quantity, from BatchFormulaLine
    assert "[[AI DRAFT PENDING" in text
    assert "{{" not in text and "{%" not in text


def test_render_stability_summary_with_narrative_supplied(project):
    storage = InMemoryStorageClient()
    conclusion = "Supports the declared 24-month shelf life per ICH Q1A(R2)."
    result = render_section(
        "3.2.P.8.1", project, narrative={"conclusion": conclusion}, storage=storage
    )

    text = _document_text(storage.get(result.storage_key))
    assert "24 months" in text  # declared shelf life
    assert "30C/65%RH" in text  # stability study condition, from StabilityStudy row
    assert conclusion in text
    assert "[[AI DRAFT PENDING" not in text  # narrative was supplied, no placeholder


def test_rendered_docx_is_a_valid_zip(project):
    storage = InMemoryStorageClient()
    result = render_section("3.2.P.1", project, storage=storage)
    # a .docx is a zip archive -- this is the cheapest possible check that
    # docxtpl produced a well-formed document, not just non-empty bytes.
    with zipfile.ZipFile(io.BytesIO(storage.get(result.storage_key))) as zf:
        assert "word/document.xml" in zf.namelist()
