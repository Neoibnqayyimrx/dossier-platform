"""Tests for the expanded DosageForm enum: every new member round-trips
through a real (SQLite) database, and R02's narrative-consistency check
correctly recognizes the new forms via the expanded _FORM_WORDS mapping."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.validation.rules  # noqa: F401  registers rules
from app.models import Base, DosageForm, Product, Project, Region, Section
from app.seed import attach_owner
from app.validation.engine import run_all


def test_every_dosage_form_round_trips_through_the_database():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)

    for form in DosageForm:
        product = Product(brand_name=f"TEST-{form.name}", generic_name="Testolol", dosage_form=form)
        attach_owner(product, None)
        session.add(product)
    session.commit()

    stored = {p.dosage_form for p in session.query(Product).all()}
    assert stored == set(DosageForm)


def _project_with_narrative(dosage_form: DosageForm, narrative_text: str) -> Project:
    product = Product(brand_name="TESTOX", generic_name="Testolol", dosage_form=dosage_form)
    attach_owner(product, None)
    project = Project(name="TESTOX filing", region=Region.NAFDAC, product=product)
    project.sections.append(
        Section(number="3.2.P.1", title="Description & Composition", narrative_text=narrative_text)
    )
    return project


def test_r02_catches_a_mismatch_on_a_new_dosage_form():
    # declared a suppository, but the narrative describes a tablet -- a
    # copy-paste bug the ORIGINAL 8-member enum couldn't even represent.
    project = _project_with_narrative(
        DosageForm.SUPPOSITORY, "Each tablet contains the active ingredient..."
    )
    report = run_all(project)
    r02 = [f for f in report.findings if f.rule_id == "R02"]
    assert len(r02) == 1
    assert "tablet" in r02[0].message.lower()


def test_r02_passes_when_a_new_dosage_form_matches_its_narrative():
    project = _project_with_narrative(
        DosageForm.TRANSDERMAL_PATCH, "Each patch releases the active ingredient over 24 hours."
    )
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R02"]
