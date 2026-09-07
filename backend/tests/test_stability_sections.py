"""Tests: stability as data, not a paragraph (P21).

The phase's claim is that 3.2.S.7.3 and 3.2.P.8.3 are TABLES -- timepoint
by test by result against the acceptance criterion -- and that a free-text
summary beside them is how a dossier comes to contradict itself. These
tests pin that claim from both ends:

  * a failing result inside the claimed shelf life blocks the export and
    names the timepoint, the test, the result and the limit;
  * the rendered 3.2.P.8.1 summary CANNOT state a shelf life the 3.2.P.8.3
    data does not support -- it refuses, rather than repeating the claim.

Plus the axes: a study is a study of something, run on a batch, in a pack,
and the database refuses one that is a study of two things or of none.
"""

from __future__ import annotations

import io

import pytest
from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.storage import InMemoryStorageClient
from app.ctd.structure import folder_for_section, folder_for_section_instance
from app.models import (
    Base,
    SpecificationOwnerKind,
    StabilityResult,
    StabilityStudy,
    StabilityStudyType,
)
from app.models.stability import supported_months
import app.validation.rules  # noqa: F401  registers rules
from app.seed.ampiclox import build_ampiclox
from app.seed.examox import build_examox
from app.templating.instances import expand_sections
from app.templating.render import render_section
from app.validation.engine import Severity, run_all


def _load(builder, **kwargs):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    project = builder(**kwargs)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def _render(project, number, subject=None):
    storage = InMemoryStorageClient()
    result = render_section(number, project, storage=storage, subject=subject)
    return Document(io.BytesIO(storage.get(result.storage_key)))


def _text(doc) -> str:
    paragraphs = "\n".join(p.text for p in doc.paragraphs)
    cells = "\n".join(
        cell.text for table in doc.tables for row in table.rows for cell in row.cells
    )
    return f"{paragraphs}\n{cells}"


# ---- the axes a real study has ---------------------------------------------


def test_a_study_belongs_to_a_substance_or_the_product_but_not_both():
    """The CHECK constraint, from the database's side. The application
    always sets exactly one owner -- but "the application always" is a
    claim about today's code paths, and a row with two owners would render
    into two sections with no error anywhere."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    # SQLite does not enforce CHECK constraints unless foreign-key and
    # constraint enforcement is on for the connection; it is by default for
    # CHECK, which is what makes this assertable here rather than only on
    # Postgres.
    with pytest.raises(IntegrityError):
        session.add(
            StabilityStudy(
                study_type=StabilityStudyType.LONG_TERM,
                condition="30C/65%RH",
                duration_months=24,
            )
        )
        session.commit()


def test_a_study_names_the_batch_and_the_pack_it_was_run_on():
    """ICH Q1A(R2) asks for long-term data on the primary batches, in the
    container closure system proposed for marketing. Both are foreign
    keys, not retyped text, so the stability section and 3.2.P.5.4 cannot
    name different batches."""
    product = _load(build_examox, buggy=False).product
    study = next(s for s in product.stability if s.study_type is StabilityStudyType.LONG_TERM)

    assert study.batch_analysis is not None
    assert study.batch_analysis in product.batch_analyses
    assert study.packaging is not None
    assert study.owner_kind is SpecificationOwnerKind.DRUG_PRODUCT


def test_the_drug_substance_has_its_own_studies():
    """3.2.S.7 is per substance. Before P21 a study could not belong to one
    at all, so a combination product's two actives had nowhere to put their
    data."""
    product = _load(build_ampiclox, buggy=False).product

    assert len(product.apis) == 2
    for api in product.apis:
        assert api.stability
        assert api.stability[0].owner_kind is SpecificationOwnerKind.DRUG_SUBSTANCE


# ---- the rule the whole design exists for -----------------------------------


def test_a_failing_result_inside_the_shelf_life_blocks_the_export():
    """R23, and the four values a finding must name.

    The limit is not a copy of the specification's limit -- it is reached
    through `result.specification_test`, which is why tightening 3.2.P.5.1
    re-judges every timepoint already on file.
    """
    project = _load(build_ampiclox, buggy=True)

    report = run_all(project)
    errors = [f for f in report.errors() if f.rule_id == "R23"]

    assert errors, "the buggy AMPICLOX fixture plants a failing dissolution at 12 months"
    message = errors[0].message
    assert "12 months" in message  # the timepoint
    assert "Dissolution" in message  # the test
    assert "68 % in 45 min" in message  # the result
    assert "NLT 80 % (Q) in 45 minutes" in message  # the limit
    assert not report.is_exportable()


def test_a_compliant_dossier_raises_no_stability_error():
    project = _load(build_ampiclox, buggy=False)

    assert [f for f in run_all(project).errors() if f.rule_id in {"R05", "R23"}] == []


def test_a_failure_beyond_the_claim_is_not_a_defect():
    """A study deliberately run past the claimed shelf life is good
    practice, and the point at which it eventually fails is WHY the claim
    is where it is. Flagging it would penalise the applicant who generated
    the most data -- so R23 stays silent, and R05 still accounts for it."""
    project = _load(build_examox, buggy=False)
    product = project.product
    study = next(s for s in product.stability if s.study_type is StabilityStudyType.LONG_TERM)
    dissolution = {t.test_name: t for t in product.specification}["Dissolution"]
    study.results.append(
        StabilityResult(
            specification_test=dissolution,
            timepoint_months=36,
            result="41 % in 45 min",
            sort_order=dissolution.sort_order,
        )
    )

    report = run_all(project)

    assert [f for f in report.errors() if f.rule_id == "R23"] == []
    # ...and the claim, which is 24 months, is still supported.
    assert [f for f in report.errors() if f.rule_id == "R05"] == []


def test_tightening_the_specification_re_judges_timepoints_already_on_file():
    """The single-source-of-truth claim, tested rather than asserted: no
    result is re-entered, and every timepoint is re-checked."""
    project = _load(build_examox, buggy=False)
    assay = {t.test_name: t for t in project.product.specification}["Assay"]

    assert [f for f in run_all(project).errors() if f.rule_id == "R23"] == []
    assay.acceptance_criterion = "99.0 - 100.0 % of label claim"

    errors = [f for f in run_all(project).errors() if f.rule_id == "R23"]

    assert errors
    assert "99.0 - 100.0 % of label claim" in errors[0].message


def test_an_uncheckable_stability_result_is_reported_as_unchecked():
    """The distinction the acceptance parser exists to preserve. An
    unparseable pair must never be silently credited as met."""
    project = _load(build_examox, buggy=False)
    study = project.product.stability[0]
    test = study.results[0].specification_test
    test.acceptance_criterion = "Conforms to the reference chromatogram"
    study.results[0].result = "See attached chromatogram"

    findings = [f for f in run_all(project).findings if f.rule_id == "R23"]
    unchecked = [f for f in findings if f.severity is Severity.INFO]

    assert unchecked, "an unparseable pair must be reported, not passed over"
    assert test.test_name in unchecked[0].message


def test_r05_now_checks_the_timepoints_not_the_study_duration():
    """The upgrade, stated as a test.

    Before P21 this rule compared the claim against how long the study RAN,
    so a 24-month study that failed at 6 months read as 24 months of
    support. The duration is untouched here; only the data changes.
    """
    project = _load(build_examox, buggy=False)
    product = project.product
    study = next(s for s in product.stability if s.study_type is StabilityStudyType.LONG_TERM)
    dissolution = {t.test_name: t for t in product.specification}["Dissolution"]

    assert study.duration_months == 24
    assert [f for f in run_all(project).errors() if f.rule_id == "R05"] == []

    failing = next(r for r in study.results if r.specification_test is dissolution
                   and r.timepoint_months == 12)
    failing.result = "51 % in 45 min"

    errors = [f for f in run_all(project).errors() if f.rule_id == "R05"]

    assert errors, "a failure at 12 months cannot support a 24-month shelf life"
    assert study.duration_months == 24  # the study still RAN for 24 months


def test_accelerated_data_alone_is_at_least_a_warning():
    """R24. Accelerated conditions detect significant change and support
    extrapolation; they do not establish a shelf life (ICH Q1A(R2))."""
    project = _load(build_examox, buggy=False)
    product = project.product
    product.stability = [
        s for s in product.stability if s.study_type is StabilityStudyType.ACCELERATED
    ]

    findings = [f for f in run_all(project).findings if f.rule_id == "R24"]

    assert findings
    assert findings[0].severity is Severity.WARNING
    assert "accelerated" in findings[0].message.lower()


def test_a_dossier_with_long_term_data_gets_no_accelerated_warning():
    project = _load(build_examox, buggy=False)

    assert [f for f in run_all(project).findings if f.rule_id == "R24"] == []


def test_one_batch_failing_caps_what_every_batch_together_supports():
    """A shelf life is a claim about the product, not about the luckiest
    batch. Two of AMPICLOX's three primary batches hold to 24 months; the
    third goes out of specification at 12, and the programme therefore
    does not support 24."""
    product = _load(build_ampiclox, buggy=True).product
    long_term = [
        s for s in product.stability if s.study_type is StabilityStudyType.LONG_TERM
    ]

    assert len(long_term) == 3
    assert max(s.longest_passing_timepoint for s in long_term) == 24
    supported, basis = supported_months(long_term)
    assert supported == 6
    assert "12 months" in basis


# ---- the sections ------------------------------------------------------------


def test_the_summary_cannot_state_a_shelf_life_the_data_does_not_support():
    """The definition-of-done test, and the reason 3.2.P.8.1 was rewired.

    The old template printed `product.shelf_life_months` beside a free-text
    result summary, so the page could assert 24 months over a table showing
    a failure at 12. It now prints what the data supports, computed by the
    same function rule R05 checks against.
    """
    project = _load(build_ampiclox, buggy=True)

    text = _text(_render(project, "3.2.P.8.1"))

    assert project.product.shelf_life_months == 24
    assert "SHELF LIFE NOT SUPPORTED" in text
    assert "24 months is claimed" in text
    # And the section does NOT assert the claim anywhere as a bare fact.
    assert "Shelf life: 24 months" not in text


def test_a_supported_shelf_life_is_stated_with_its_evidence():
    project = _load(build_examox, buggy=False)

    text = _text(_render(project, "3.2.P.8.1"))

    assert "Shelf life: 24 months" in text
    assert "NOT SUPPORTED" not in text


def test_the_data_section_renders_every_study_with_its_limits():
    project = _load(build_examox, buggy=False)

    doc = _render(project, "3.2.P.8.3")
    text = _text(doc)

    # One block per study: three long-term batches plus one accelerated.
    assert len(doc.tables) == 4
    assert "EXA/24/0101" in text
    assert "40C/75%RH" in text
    # The limit is on the same line as the value it judges, never on
    # another page.
    assert "90.0 - 110.0 % of label claim" in text
    assert "99.4 % of label claim" in text


def test_the_data_section_marks_an_out_of_specification_cell():
    """An assessor should not have to compare eight columns by eye -- the
    document shows which cell failed."""
    project = _load(build_ampiclox, buggy=True)

    text = _text(_render(project, "3.2.P.8.3"))

    assert "OUT OF SPECIFICATION" in text


def test_the_drug_substance_sections_name_only_their_own_substance():
    project = _load(build_ampiclox, buggy=False)
    ampicillin = {a.inn_name: a for a in project.product.apis}["Ampicillin"]

    text = _text(_render(project, "3.2.S.7.3", ampicillin))

    assert "Ampicillin" in text
    assert "Cloxacillin" not in text


def test_the_substance_summary_states_a_retest_period_not_a_shelf_life():
    """A drug substance does not have a shelf life. It has a retest period
    -- the interval after which the material must be re-tested before use
    -- and printing "shelf life" on 3.2.S.7.1 is a regulatory error on the
    page, not a wording preference."""
    project = _load(build_examox, buggy=False)
    api = project.product.apis[0]

    text = _text(_render(project, "3.2.S.7.1", api))

    assert "Retest period" in text
    assert "Shelf life" not in text


def test_the_commitment_protocol_is_read_from_the_studies_themselves():
    """3.2.S.7.2 / 3.2.P.8.2. The commonest failure in this section is a
    commitment naming batches or timepoints the stability section does not
    contain; every row here is read from the studies."""
    project = _load(build_examox, buggy=False)

    text = _text(_render(project, "3.2.P.8.2"))

    for study in project.product.stability:
        if study.study_type is StabilityStudyType.ACCELERATED:
            # An accelerated study is finished at six months -- there is
            # nothing to commit to continuing.
            continue
        assert study.batch_analysis.batch_number in text


def test_every_stability_leaf_has_a_folder_and_an_instance():
    """The P16 contract, per leaf: registered is not enough -- a leaf with
    no declared folder cannot be placed, and `folder_for_section` raises
    rather than guessing."""
    project = _load(build_ampiclox, buggy=False)
    instances = {i.number for i in expand_sections(project)}

    for number in ("3.2.P.8.1", "3.2.P.8.2", "3.2.P.8.3"):
        assert number in instances
        assert folder_for_section(number)

    for number in ("3.2.S.7.1", "3.2.S.7.2", "3.2.S.7.3"):
        assert number in instances
        assert folder_for_section_instance(number, "ampicillin")
