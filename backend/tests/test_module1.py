"""Tests for the P08 Module 1 foundation: Applicant/Declaration models, the
registration-form template (section 1.2), the declaration placeholder
renderer, and rules R14-R16.
"""

from __future__ import annotations

import io
from datetime import date

import pytest
from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.validation.rules  # noqa: F401  registers rules
from app.core.storage import InMemoryStorageClient
from app.models import (
    Applicant,
    Base,
    Declaration,
    DeclarationType,
)
from app.seed import same_owner_as
from app.seed.documents import attach_certificate_documents
from app.seed.examox import build_examox
from app.templating.declarations import render_declaration
from app.templating.render import render_section
from app.validation.engine import Severity, run_all


def _document_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


@pytest.fixture
def project():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    project = build_examox(buggy=False)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


# ---- Applicant / Declaration models ----------------------------------------


def test_seed_project_has_an_applicant_and_two_declarations(project):
    assert project.applicant is not None
    assert project.applicant.company_name == "Exagon Pharmaceuticals Ltd"
    types = {d.declaration_type for d in project.declarations}
    assert types == {
        DeclarationType.POWER_OF_ATTORNEY,
        DeclarationType.DECLARATION_OF_AUTHENTICITY,
    }


def test_applicant_is_reusable_across_projects():
    """Same shape as Manufacturer/Product: an Applicant is master data, not
    nested 1:1 inside a Project -- two Project rows can point at one."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)

    p1 = build_examox(buggy=False)
    p2 = build_examox(buggy=False)
    # P15a: an Applicant carries its own owner, so a bare one no longer
    # inserts -- it belongs to whoever owns the product it is filed with.
    applicant = Applicant(company_name="Shared Applicant Ltd", **same_owner_as(p1.product))
    p1.applicant = applicant
    p2.applicant = applicant
    session.add_all([p1, p2])
    session.commit()
    session.refresh(applicant)

    assert len(applicant.projects) == 2


# ---- Registration form template (section 1.2.2) ----------------------------


def test_registration_form_fills_applicant_and_product_data(project):
    storage = InMemoryStorageClient()
    result = render_section("1.2.2", project, storage=storage)

    text = _document_text(storage.get(result.storage_key))
    assert "NAFDAC" in text
    assert "EXAMOX" in text
    assert "Exagon Pharmaceuticals Ltd" in text
    assert "Aisha Bello" in text
    assert "{{" not in text and "{%" not in text


def test_registration_form_falls_back_when_applicant_missing():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    project = build_examox(buggy=False)
    project.applicant = None
    session.add(project)
    session.commit()
    session.refresh(project)

    storage = InMemoryStorageClient()
    result = render_section("1.2.2", project, storage=storage)

    text = _document_text(storage.get(result.storage_key))
    assert "[[NOT YET ON FILE]]" in text


# ---- Declaration placeholder renderer ---------------------------------------


def _persisted_declaration(project, **kwargs) -> Declaration:
    declaration = Declaration(project_id=project.id, **kwargs)
    return declaration


def test_declaration_placeholder_names_type_and_requires_signature(project):
    declaration = _persisted_declaration(
        project, declaration_type=DeclarationType.POWER_OF_ATTORNEY
    )
    storage = InMemoryStorageClient()

    result = render_declaration(declaration, project, storage=storage)

    text = _document_text(storage.get(result.storage_key))
    assert "Power Of Attorney" in text
    assert "Exagon Pharmaceuticals Ltd" in text
    assert "ACTION REQUIRED" in text
    assert "notarized" in text.lower()
    assert result.storage_key == f"projects/{project.id}/declarations/{declaration.id}.docx"


def test_declaration_of_authenticity_does_not_require_notarization(project):
    declaration = _persisted_declaration(
        project, declaration_type=DeclarationType.DECLARATION_OF_AUTHENTICITY
    )
    storage = InMemoryStorageClient()

    result = render_declaration(declaration, project, storage=storage)

    text = _document_text(storage.get(result.storage_key))
    assert "notarized" not in text.lower()


# ---- R14: NAFDAC requires an applicant --------------------------------------


def test_r14_flags_missing_applicant():
    project = build_examox(buggy=False)
    project.applicant = None
    report = run_all(project)
    r14 = [f for f in report.findings if f.rule_id == "R14"]
    assert len(r14) == 1
    assert r14[0].severity is Severity.ERROR


def test_r14_passes_with_an_applicant():
    project = build_examox(buggy=False)
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R14"]


# ---- R15: attached declarations must be signed (notarized is a nudge) ------


def test_r15_flags_an_unsigned_declaration():
    project = build_examox(buggy=False)
    project.declarations.append(
        Declaration(declaration_type=DeclarationType.GMP_COMPLIANCE_UNDERTAKING, signed=False)
    )
    report = run_all(project)
    r15 = [f for f in report.findings if f.rule_id == "R15"]
    assert any(f.severity is Severity.ERROR for f in r15)


def test_r15_warns_on_signed_but_not_notarized_when_required():
    project = build_examox(buggy=False)
    project.declarations.append(
        Declaration(
            declaration_type=DeclarationType.GMP_COMPLIANCE_UNDERTAKING,
            signed=True,
            signed_date=date(2026, 1, 20),
            notarized=False,
        )
    )
    report = run_all(project)
    r15 = [f for f in report.findings if f.rule_id == "R15"]
    assert len(r15) == 1
    assert r15[0].severity is Severity.WARNING


def test_r15_does_not_require_notarization_for_declaration_of_authenticity():
    """The seed's Declaration of Authenticity is signed but not notarized --
    R15 must not warn on it, since that type never requires notarization."""
    project = build_examox(buggy=False)
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R15"]


# ---- R16: NAFDAC requires specific declarations to be present --------------


def test_r16_flags_missing_required_declarations():
    project = build_examox(buggy=False)
    project.declarations.clear()
    report = run_all(project)
    r16 = [f for f in report.findings if f.rule_id == "R16"]
    assert len(r16) == 1
    assert "power-of-attorney" in r16[0].message
    assert "declaration-of-authenticity" in r16[0].message


def test_r16_passes_when_both_required_declarations_present():
    project = build_examox(buggy=False)
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R16"]


def test_examox_clean_project_still_fully_exportable():
    """Sanity: adding R14-R16 doesn't regress the existing 'a clean project
    passes validation' guarantee test_seed_demo.py already covers."""
    project = build_examox(buggy=False)
    # P18: "fully exportable" now includes having the certificate documents
    # attached, not merely the certificate rows -- R20 is the rule that
    # makes the difference, and a fixture modelling a finished filing has
    # both.
    attach_certificate_documents(project, InMemoryStorageClient())
    report = run_all(project)
    assert report.is_exportable()


# ---- P24e: the invariant that keeps a regional leaf regional ----------------


def test_every_module_1_section_is_placeable_in_every_region():
    """A Module 1 leaf must either have a slot in a region, or be declared
    conditional so that region never emits it.

    Module 1 is the regional module, so a section registered without a slot
    somewhere is not a hypothetical: it is a build that raises. Placement in
    Modules 2-5 comes from one shared folder map, but Module 1's comes from
    the region profile, and `folder_for_section` refuses to guess -- which
    is right, and which means the failure arrives as a KeyError in the
    middle of assembling a package.

    That happened three times in P24 alone (1.2.1, 1.2.14, 1.6, then 1.4.2),
    each found by building the worked example as an EU sequence rather than
    by anything in the test suite. `SectionSpec.only_when_applicable` is the
    mechanism P22 built for exactly this and its own comment names the case;
    what was missing was something that noticed when a new leaf forgot to
    use it.
    """
    from app.ctd.region_profiles import REGION_PROFILES
    from app.templating.registry import SECTIONS

    module_1 = [
        spec for spec in SECTIONS.values() if spec.number.startswith("1.") and not spec.is_statement
    ]
    assert module_1, "no Module 1 sections registered -- this test would pass vacuously"

    unplaceable = []
    for region, profile in REGION_PROFILES.items():
        placed = {slot.section_number for slot in profile.module1_slots if slot.section_number}
        placed |= {slot.section_number for slot in profile.document_slots}
        for spec in module_1:
            if spec.number in placed:
                continue
            # gap Phase 4b: or the region declares it does not take this
            # document at all (FDA has no 1.2.2 registration form), which
            # `expand_sections` honours by never emitting it.
            if spec.number in profile.absent_module1_sections:
                continue
            # No slot here. That is fine ONLY if the section is conditional,
            # because a region with no applicability table (EU) then emits
            # nothing for it -- see app/templating/instances.py.
            if not spec.only_when_applicable:
                unplaceable.append((region.value, spec.number))

    assert not unplaceable, (
        "Module 1 sections with no slot in a region, no only_when_applicable "
        "flag and no absent_module1_sections entry, so a build for that region "
        f"raises: {sorted(unplaceable)}"
    )


def test_a_region_s_absent_sections_are_never_emitted_and_others_still_are():
    """FDA declares 1.2.2 absent; the EU files it. The same product, two
    regions, two answers -- which is why the absence belongs to the region."""
    from app.models import Region
    from app.seed.examox import build_examox
    from app.templating.instances import expand_sections

    project = build_examox()
    project.region = Region.FDA
    assert "1.2.2" not in {i.key for i in expand_sections(project)}

    project.region = Region.EU
    assert "1.2.2" in {i.key for i in expand_sections(project)}


def test_absent_sections_are_module_1_numbers_that_exist():
    """A typo here would silently absent nothing, so the declared numbers
    must be real, registered Module 1 sections."""
    from app.ctd.region_profiles import REGION_PROFILES
    from app.templating.registry import SECTIONS

    for profile in REGION_PROFILES.values():
        for number in profile.absent_module1_sections:
            assert number in SECTIONS and number.startswith("1."), (profile.region, number)
