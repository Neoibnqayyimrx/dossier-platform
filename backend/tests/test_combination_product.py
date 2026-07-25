"""Tests: AMPICLOX (a fixed-dose combination -- ampicillin + cloxacillin)
proves the data model and rule engine handle more than one active
ingredient per product, not just the single-API shape every other seed
fixture (EXAMOX, LAMOX) happens to have.

Strength moved from Product to ActiveIngredient specifically so a second
active has somewhere to put its own strength; R01/R04 were rewritten to
loop over every API rather than assuming `apis[0]` -- these tests are the
proof that rewrite actually works, not just that it doesn't crash.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
import app.validation.rules  # noqa: F401  registers rules
from app.validation.engine import run_all
from app.seed.ampiclox import build_ampiclox


def _load(buggy: bool = True):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    project = build_ampiclox(buggy=buggy)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def test_seed_ampiclox_has_two_active_ingredients_each_with_own_strength():
    product = _load(buggy=False).product
    assert len(product.apis) == 2
    by_name = {api.inn_name: api for api in product.apis}
    assert float(by_name["Ampicillin"].strength_value) == 250.0
    assert float(by_name["Cloxacillin"].strength_value) == 250.0
    assert product.strength_display == "Ampicillin 250 mg + Cloxacillin 250 mg"


def test_r01_catches_a_defect_on_the_second_active_ingredient():
    """The buggy fixture's ONLY defect is Cloxacillin's narrative strength
    (125mg instead of 250mg) -- Ampicillin's narrative strength is correct.
    The old R01 (product.strength_value / product.generic_name, singular)
    could never have caught this; it would have had no idea "Cloxacillin"
    existed at all."""
    report = run_all(_load(buggy=True))
    r01 = [f for f in report.findings if f.rule_id == "R01"]
    assert len(r01) == 1
    assert "Cloxacillin" in r01[0].message
    assert "125" in r01[0].message and "250" in r01[0].message
    # and Ampicillin, which IS correct in the buggy fixture, is not flagged
    assert not any("Ampicillin" in f.message for f in r01)


def test_corrected_ampiclox_passes_r01():
    report = run_all(_load(buggy=False))
    assert not [f for f in report.findings if f.rule_id == "R01"]


def test_r04_reconciles_each_active_against_its_own_salt_factor():
    """Ampicillin (salt factor 1.155) and Cloxacillin (salt factor 1.092)
    are different -- if R04 wrongly used apis[0]'s factor for every batch
    line (the pre-fix behavior), one of these two correctly-declared
    quantities would spuriously fail reconciliation."""
    report = run_all(_load(buggy=False))
    assert not [f for f in report.findings if f.rule_id == "R04"]


def test_r04_flags_a_genuine_mismatch_using_the_right_salt_factor():
    project = _load(buggy=False)
    cloxacillin_line = next(
        line for line in project.product.batch_formula if "Cloxacillin" in line.component
    )
    cloxacillin_line.declared_batch_qty_kg = 999.0  # obviously wrong

    report = run_all(project)
    r04 = [f for f in report.findings if f.rule_id == "R04"]
    assert len(r04) == 1
    assert "Cloxacillin" in r04[0].message
    # computed using Cloxacillin's OWN 1.092 salt factor (250mg * 1.092 *
    # 100,000 / 1e6 = 27.3 kg) -- not Ampicillin's 1.155, which would give
    # a different (wrong) number and prove the FK linkage isn't being read.
    assert "27.3" in r04[0].message
