"""Tests for app.templating.certificates: a Certificate that has no real
file attached yet gets a clearly-marked placeholder .docx at the right
storage path, never fabricated content standing in for the real thing."""

from __future__ import annotations

import io

from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.storage import InMemoryStorageClient
from app.models import Base, Certificate, CertificateType
from app.seed.examox import build_examox
from app.templating.certificates import render_certificate_placeholder


def _persisted_certificate(**kwargs) -> Certificate:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    project = build_examox(buggy=False)
    session.add(project)
    session.commit()
    session.refresh(project)

    certificate = Certificate(product_id=project.product.id, **kwargs)
    session.add(certificate)
    session.commit()
    session.refresh(certificate)
    return certificate


def _document_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def test_placeholder_names_the_certificate_type_and_missing_fields():
    certificate = _persisted_certificate(certificate_type=CertificateType.CPP)
    storage = InMemoryStorageClient()

    result = render_certificate_placeholder(certificate, storage=storage)

    text = _document_text(storage.get(result.storage_key))
    assert "CPP" in text
    assert "REPLACE THIS FILE" in text
    assert "(not yet obtained)" in text
    assert "(not yet known)" in text


def test_placeholder_includes_known_fields_when_present():
    certificate = _persisted_certificate(
        certificate_type=CertificateType.GMP,
        issuing_authority="NAFDAC",
        certificate_number="NAFDAC/GMP/2026/0042",
    )
    storage = InMemoryStorageClient()

    result = render_certificate_placeholder(certificate, storage=storage)

    text = _document_text(storage.get(result.storage_key))
    assert "GMP" in text
    assert "NAFDAC" in text
    assert "NAFDAC/GMP/2026/0042" in text


def test_placeholder_storage_key_is_scoped_by_product():
    certificate = _persisted_certificate(certificate_type=CertificateType.CEP)
    storage = InMemoryStorageClient()

    result = render_certificate_placeholder(certificate, storage=storage)

    assert result.storage_key == (
        f"products/{certificate.product_id}/certificates/{certificate.id}.docx"
    )
