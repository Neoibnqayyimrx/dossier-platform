"""Tests for P06's rule engine additions: R04-R13 (one pass/fail fixture
each, per the phase's own "small, independently testable" design note),
region-aware filtering, the export-override mechanism, and category
aggregation.

Built from plain, directly-constructed objects -- no DB session at all.
Rules only ever read attributes already set on the object graph, and a
transient (never-added-to-a-session) SQLAlchemy object graph is a fully
valid Python object graph on its own; relationships set via constructor
kwargs or .append() work with zero database involvement. This is a
deliberately different, lighter-weight style than test_validation.py's
sqlite-session-backed LAMOX fixture -- both are valid, this one is just
closer to a pure unit test.
"""

from __future__ import annotations

from datetime import date, timedelta

import app.validation.rules  # noqa: F401  registers rules
from app.validation.engine import Severity, run_all
from app.models import (
    SpecificationTest,
    Product,
    Project,
    Manufacturer,
    ActiveIngredient,
    Packaging,
    StabilityStudy,
    Certificate,
    DosageForm,
    RegistrationType,
    Region,
    ManufacturerRole,
    CompendialStatus,
    CertificateType,
    GMPStatus,
    PackagingComponent,
    StabilityStudyType,
    BatchFormulaLine,
)


def _minimal_project(**product_kwargs) -> Project:
    product_kwargs.setdefault("shelf_life_months", 24)
    product = Product(
        brand_name="TESTOX",
        generic_name="Testolol",
        dosage_form=DosageForm.TABLET,
        registration_type=RegistrationType.RENEWAL,
        country="Nigeria",
        **product_kwargs,
    )
    return Project(name="TESTOX filing", region=Region.NAFDAC, product=product)


# ---- R04: salt/base batch arithmetic ---------------------------------------


def test_r04_flags_a_genuine_batch_arithmetic_mismatch():
    project = _minimal_project()
    api = ActiveIngredient(
        inn_name="Testolol", strength_value=100, strength_unit="mg", salt_factor=1.0
    )
    project.product.apis.append(api)
    project.product.batch_formula.append(
        BatchFormulaLine(
            component="Testolol",
            is_active=True,
            active_ingredient=api,
            spec="BP",
            qty_per_unit_mg=100.0,
            batch_size_units=10_000,
            declared_batch_qty_kg=5.0,  # correct is 100*1.0*10,000/1e6 = 1.0 kg
        )
    )
    report = run_all(project)
    r04 = [f for f in report.findings if f.rule_id == "R04"]
    assert len(r04) == 1
    assert "1.0" in r04[0].message


# ---- R05: shelf life vs. stability ------------------------------------------


def test_r05_flags_shelf_life_exceeding_stability():
    """A study with no timepoint results still falls back to its declared
    duration, which is exactly the pre-P21 behaviour -- and the finding now
    says so, so a filer can tell "we checked every timepoint" apart from
    "we took your word for how long the study ran"."""
    project = _minimal_project(shelf_life_months=36)
    project.product.stability.append(
        StabilityStudy(
            study_type=StabilityStudyType.LONG_TERM,
            condition="30C/65%RH",
            duration_months=24,
        )
    )
    report = run_all(project)
    r05 = [f for f in report.findings if f.rule_id == "R05"]
    assert len(r05) == 1
    assert "36" in r05[0].message and "24" in r05[0].message
    assert "no timepoint results are on file" in r05[0].message


def test_r05_ignores_an_accelerated_study_when_counting_support():
    """A latent bug P21 fixed. The old rule ran `max()` over EVERY study on
    file, so a six-month accelerated study counted as six months of
    shelf-life support. Accelerated conditions detect significant change;
    they do not establish a shelf life (ICH Q1A(R2))."""
    project = _minimal_project(shelf_life_months=6)
    project.product.stability.append(
        StabilityStudy(
            study_type=StabilityStudyType.ACCELERATED,
            condition="40C/75%RH",
            duration_months=6,
        )
    )
    report = run_all(project)

    assert [f for f in report.findings if f.rule_id == "R05"]
    # ...and R24 says WHY the data does not count, which R05 cannot.
    assert [f for f in report.findings if f.rule_id == "R24"]


# ---- R06: bioequivalence required for a generic -----------------------------


def test_r06_flags_missing_bioequivalence():
    report = run_all(_minimal_project())  # no clinical entries at all
    assert any(f.rule_id == "R06" for f in report.findings)


# ---- R07: API specification present -----------------------------------------


def test_r07_flags_missing_api_specification():
    project = _minimal_project()
    project.product.apis.append(ActiveIngredient(inn_name="Testolol", specification=[]))
    report = run_all(project)
    assert any(f.rule_id == "R07" for f in report.findings)


def test_r07_passes_when_specification_present():
    project = _minimal_project()
    project.product.apis.append(
        ActiveIngredient(
            inn_name="Testolol",
            specification=[
                SpecificationTest(
                    test_name="Assay",
                    method="HPLC, BP monograph",
                    acceptance_criterion="95.0 - 105.0 % w/w",
                )
            ],
        )
    )
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R07"]


# ---- R08: manufacturer GMP status certified ---------------------------------


def test_r08_flags_an_uncertified_manufacturer():
    project = _minimal_project()
    project.product.manufacturers.append(
        Manufacturer(
            name="Site A", role=ManufacturerRole.FINISHED_PRODUCT, gmp_status=GMPStatus.EXPIRED
        )
    )
    report = run_all(project)
    r08 = [f for f in report.findings if f.rule_id == "R08"]
    assert len(r08) == 1
    assert "expired" in r08[0].message.lower()


def test_r08_passes_when_certified():
    project = _minimal_project()
    project.product.manufacturers.append(
        Manufacturer(
            name="Site A", role=ManufacturerRole.FINISHED_PRODUCT, gmp_status=GMPStatus.CERTIFIED
        )
    )
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R08"]


# ---- R09: API manufacturer role integrity -----------------------------------


def test_r09_flags_an_api_linked_to_the_wrong_role_manufacturer():
    project = _minimal_project()
    finished_site = Manufacturer(name="Finished Site", role=ManufacturerRole.FINISHED_PRODUCT)
    project.product.manufacturers.append(finished_site)
    project.product.apis.append(ActiveIngredient(inn_name="Testolol", manufacturer=finished_site))
    report = run_all(project)
    r09 = [f for f in report.findings if f.rule_id == "R09"]
    assert len(r09) == 1


def test_r09_passes_when_linked_to_an_api_manufacturer():
    project = _minimal_project()
    api_site = Manufacturer(name="API Site", role=ManufacturerRole.API_MANUFACTURER)
    project.product.manufacturers.append(api_site)
    project.product.apis.append(ActiveIngredient(inn_name="Testolol", manufacturer=api_site))
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R09"]


# ---- R10: ICH Q3C residual solvent limits -----------------------------------


def test_r10_flags_a_solvent_level_above_its_q3c_limit():
    project = _minimal_project()
    project.product.apis.append(
        ActiveIngredient(inn_name="Testolol", residual_solvents="Methanol: 3500 ppm")
    )
    report = run_all(project)
    r10 = [f for f in report.findings if f.rule_id == "R10"]
    assert len(r10) == 1
    assert "methanol" in r10[0].message.lower()


def test_r10_passes_when_within_limit():
    project = _minimal_project()
    project.product.apis.append(
        ActiveIngredient(inn_name="Testolol", residual_solvents="Methanol: 500 ppm")
    )
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R10"]


# ---- R11: pharmacopoeial version reminder (always INFO, never blocks) ------


def test_r11_reminds_to_verify_the_pharmacopoeia_edition():
    project = _minimal_project()
    project.product.apis.append(
        ActiveIngredient(inn_name="Testolol", compendial_std=CompendialStatus.BP)
    )
    report = run_all(project)
    r11 = [f for f in report.findings if f.rule_id == "R11"]
    assert len(r11) == 1
    assert r11[0].severity == Severity.INFO


# ---- R12: pack size matches packaging ---------------------------------------


def test_r12_flags_a_pack_size_mismatch():
    project = _minimal_project(pack_size="10x10 blister")
    project.product.packaging.append(
        Packaging(component=PackagingComponent.CARTON, description="Printed carton, 5x10 blister")
    )
    report = run_all(project)
    assert len([f for f in report.findings if f.rule_id == "R12"]) == 1


def test_r12_passes_when_pack_size_is_mentioned():
    project = _minimal_project(pack_size="10x10 blister")
    project.product.packaging.append(
        Packaging(component=PackagingComponent.CARTON, description="Printed carton, 10x10 blister")
    )
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R12"]


# ---- R13: NAFDAC-only CPP certificate requirement + region filtering --------


def test_r13_flags_a_missing_cpp_for_a_nafdac_project():
    report = run_all(_minimal_project())  # NAFDAC region, no certificates at all
    r13 = [f for f in report.findings if f.rule_id == "R13"]
    assert len(r13) == 1
    assert "CPP" in r13[0].message


def test_r13_flags_an_expired_cpp():
    project = _minimal_project()
    project.product.certificates.append(
        Certificate(
            certificate_type=CertificateType.CPP, expiry_date=date.today() - timedelta(days=1)
        )
    )
    report = run_all(project)
    assert len([f for f in report.findings if f.rule_id == "R13"]) == 1


def test_r13_passes_with_an_unexpired_cpp():
    project = _minimal_project()
    project.product.certificates.append(
        Certificate(
            certificate_type=CertificateType.CPP, expiry_date=date.today() + timedelta(days=365)
        )
    )
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R13"]


def test_r13_does_not_apply_outside_nafdac():
    """Region filtering in action: an FDA project with NO certificate at
    all must not trigger R13 -- it's NAFDAC-only, proving `run_all` really
    does skip a rule outright for a non-applicable region, not just
    happen to pass it."""
    project = _minimal_project()
    project.region = Region.FDA
    report = run_all(project)
    assert not [f for f in report.findings if f.rule_id == "R13"]


# ---- Report: override mechanism + category aggregation ----------------------


def test_override_makes_an_error_non_blocking():
    report = run_all(_minimal_project())  # R06 + R13 errors guaranteed present
    assert not report.is_exportable()
    error_ids = frozenset(f.rule_id for f in report.errors())
    assert error_ids  # sanity: there really are errors to override

    assert report.is_exportable(error_ids)
    assert report.errors(error_ids) == []
    # overriding does not erase the finding from the report -- only from
    # what counts against the export gate.
    assert any(f.rule_id in error_ids for f in report.findings)


def test_by_category_groups_findings():
    report = run_all(_minimal_project())
    grouped = report.by_category()
    assert "completeness" in grouped
    assert all(f.category == "completeness" for f in grouped["completeness"])
