"""Tests: app/seed/examox.py builds a full EXAMOX project (P01 task 5/6),
structured exactly like app/seed/lamox.py — only branding/company details
differ. scripts/seed_demo.py persists this into the live Postgres."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
import app.validation.rules  # noqa: F401  registers rules
from app.validation.engine import run_all
from app.seed.examox import build_examox


def _load(buggy: bool = True):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    project = build_examox(buggy=buggy)
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
    assert len(product.stability) == 1
    assert len(product.clinical) >= 1
    assert len(project.sections) >= 1


def test_seed_examox_shelf_life_is_fully_supported():
    """Unlike the old Parazon fixture, EXAMOX's declared shelf life (24 months)
    is fully supported by its long-term stability study (24 months) -- no
    artificial R05 mismatch; the only planted defects are R01-R03."""
    product = _load(buggy=False).product
    longest_supported = max(s.duration_months for s in product.stability)
    assert product.shelf_life_months <= longest_supported


def test_buggy_examox_is_not_exportable():
    report = run_all(_load(buggy=True))
    assert not report.is_exportable
    ids = {f.rule_id for f in report.findings}
    assert {"R01", "R02", "R03"} <= ids  # same three defect classes as LAMOX


def test_corrected_examox_passes():
    report = run_all(_load(buggy=False))
    assert report.is_exportable
    assert report.findings == []


def test_model_round_trip():
    project = _load(buggy=False)
    assert project.product.brand_name == "EXAMOX"
    assert project.product.manufacturers[0].name == "Exagon"
    assert project.product.apis[0].salt_form == "Amoxicillin Trihydrate"
    assert project.product.stability[0].duration_months == 24
