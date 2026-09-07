"""Tests: app/seed/examox.py builds a full EXAMOX project (P01 task 5/6),
structured exactly like app/seed/lamox.py — only branding/company details
differ. scripts/seed_demo.py persists this into the live Postgres."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.storage import InMemoryStorageClient
from app.models import Base, ManufacturerRole, StabilityStudyType
from app.models.stability import supported_months
from app.seed.documents import attach_certificate_documents
import app.validation.rules  # noqa: F401  registers rules
from app.validation.engine import Severity, run_all
from app.seed.examox import build_examox


def _load(buggy: bool = True):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    project = build_examox(buggy=buggy)
    # P18: the corrected variant models a FINISHED filing, and R20 blocks
    # export while a certificate is still a placeholder. Storage here is
    # throwaway -- these tests never build a package, they only need the
    # rows the rule reads.
    attach_certificate_documents(project, InMemoryStorageClient())
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def test_seed_examox_populates_a_full_project():
    project = _load()
    product = project.product

    assert product.brand_name == "EXAMOX"
    assert len(product.manufacturers) >= 1
    assert len(product.apis) >= 1
    assert len(product.excipients) >= 2
    assert len(product.packaging) >= 1
    # P21: four studies, not one. ICH Q1A(R2) asks for long-term data on at
    # least three primary batches, so the seed builds one study PER BATCH
    # (each foreign-keyed to the batch 3.2.P.5.4 already files), plus one
    # accelerated study on the first batch.
    assert len(product.stability) == 4
    assert len(product.clinical) >= 1
    assert len(project.sections) >= 1


def test_seed_examox_shelf_life_is_fully_supported():
    """Unlike the old Parazon fixture, EXAMOX's declared shelf life (24 months)
    is fully supported by its long-term stability data -- no artificial R05
    mismatch; the only planted defects are R01-R03.

    P21 changed what "supported" means, and the test with it. It used to
    read `max(duration_months)` -- how long the longest study RAN -- which
    would credit a 24-month study that failed at 6 months with 24 months of
    support. It now asks the same function rule R05 asks: how far did the
    data actually hold, against the specification's own limits.
    """
    product = _load(buggy=False).product
    long_term = [
        s for s in product.stability if s.study_type is StabilityStudyType.LONG_TERM
    ]
    supported, _ = supported_months(long_term)
    assert product.shelf_life_months <= supported


def test_buggy_examox_is_not_exportable():
    report = run_all(_load(buggy=True))
    assert not report.is_exportable()
    ids = {f.rule_id for f in report.findings}
    assert {"R01", "R02", "R03"} <= ids  # same three defect classes as LAMOX


def test_corrected_examox_passes():
    report = run_all(_load(buggy=False))
    assert report.is_exportable()
    # a genuinely clean dossier still gets INFO reminders (R11: verify the
    # current pharmacopoeia edition) -- only ERROR/WARNING findings would
    # indicate something is actually wrong.
    assert not [f for f in report.findings if f.severity != Severity.INFO]


def test_model_round_trip():
    project = _load(buggy=False)
    assert project.product.brand_name == "EXAMOX"
    # Looked up by ROLE, not by list position: the seed now carries a
    # separate drug-substance manufacturer (rule R17), and an index-based
    # assertion silently tracked whichever happened to be appended first.
    by_role = {m.role: m for m in project.product.manufacturers}
    assert by_role[ManufacturerRole.FINISHED_PRODUCT].name == "Exagon"
    assert by_role[ManufacturerRole.API_MANUFACTURER].name == "Exagon API Division"
    assert project.product.apis[0].salt_form == "Amoxicillin Trihydrate"
    assert project.product.stability[0].duration_months == 24
