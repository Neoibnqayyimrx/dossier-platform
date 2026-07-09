"""Tests: the rule engine catches the real LAMOX bugs, and passes when fixed."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
import app.validation.rules  # noqa: F401  registers rules
from app.validation.engine import run_all
from app.seed.lamox import build_lamox
from app.templating.section_map import render_p1


def _load(buggy: bool):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    p = build_lamox(buggy=buggy)
    s.add(p)
    s.commit()
    s.refresh(p)
    return p


def test_buggy_dossier_is_not_exportable():
    report = run_all(_load(buggy=True))
    assert not report.is_exportable
    ids = {f.rule_id for f in report.findings}
    assert {"R01", "R02", "R03"} <= ids  # all three real bugs caught


def test_r01_names_the_wrong_strength():
    report = run_all(_load(buggy=True))
    r01 = [f for f in report.findings if f.rule_id == "R01"]
    assert r01 and "250 mg" in r01[0].message and "500 mg" in r01[0].message


def test_corrected_dossier_passes():
    report = run_all(_load(buggy=False))
    assert report.is_exportable
    assert report.findings == []


def test_salt_base_arithmetic_passes_for_lamox():
    # 500 mg base * 1.148 * 250000 = 143.5 kg ~ declared 144 kg -> no R04 finding
    report = run_all(_load(buggy=False))
    assert not [f for f in report.findings if f.rule_id == "R04"]


def test_rendered_section_cannot_contain_bugs():
    product = _load(buggy=False).product
    out = render_p1(product)
    assert "500 mg" in out
    assert "250 mg" not in out          # the wrong strength can't appear
    assert "tablet" not in out.lower()  # wrong dosage form can't appear


def test_model_round_trip():
    p = _load(buggy=False)
    assert p.product.brand_name == "LAMOX"
    assert p.product.apis[0].salt_form == "Amoxicillin Trihydrate"
    assert p.product.stability[0].duration_months == 24
