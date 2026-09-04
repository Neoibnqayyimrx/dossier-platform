"""P17: applicability as declared config, and the statements it owes.

The behaviour under test is easy to state and easy to get wrong: a section
that a guideline excuses is not an absent section, it is a section whose
content is a statement citing the guideline. These tests pin the four ways
that can go wrong — a statement that does not appear, a statement that
appears when the section is actually owed, a condition answered by silence,
and a submission type change that does not move anything.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.storage import InMemoryStorageClient
from app.ctd.region_profiles import (
    Applicability,
    NAFDAC_PROFILE,
    resolve_applicability,
)
from app.ctd.structure import folder_for_section
from app.models import Base, Section, SubmissionType
from app.models.enums import Region
from app.seed.examox import build_examox
from app.templating.instances import expand_sections
from app.templating.registry import SECTIONS
from app.templating.render import render_section
from app.validation.engine import run_all

# 5.3.2 is a plain declared exclusion; 3.2.P.4.6 (novel excipients) is the
# conditional one, and the pair is deliberate -- the whole point of P17 is
# that these two arrive at the same statement by different routes.
DECLARED_NA = "5.3.2"
CONDITIONAL = "3.2.P.4.6"


@pytest.fixture
async def db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def statement_numbers(project) -> set[str]:
    return {i.number for i in expand_sections(project) if i.spec.is_statement}


# ---- the table itself (pure config, no DB) ----------------------------------


def test_applicability_is_read_from_the_target_toc_not_retyped():
    """Every leaf of the contract has a row, with the YAML's own reasons.

    If this ever fails by returning fewer rows than the target TOC has
    leaves, the table has stopped being derived and someone has started
    curating it -- which is the two-truths failure the P17 prompt names.
    """
    table = NAFDAC_PROFILE.applicability_for(SubmissionType.MULTISOURCE_GENERIC)

    assert len(table) == 98
    assert table["4.0"].status is Applicability.NOT_APPLICABLE
    assert table["4.0"].citation and "multisource" in table["4.0"].citation
    assert table[CONDITIONAL].status is Applicability.CONDITIONAL
    assert table[CONDITIONAL].condition
    assert table["2.3"].status is Applicability.REQUIRED


def test_every_statement_leaf_has_a_folder_and_a_registered_section():
    """A statement with nowhere to go fails at build time, not review time.

    `folder_for_section` raises on an unmapped number by design; asserting
    it here means a future `production: na_statement` leaf added to the
    YAML cannot reach a package build before someone gives it a home.
    """
    for number, spec in SECTIONS.items():
        if spec.is_statement:
            assert folder_for_section(number)


# ---- what gets emitted ------------------------------------------------------


def test_declared_not_applicable_section_emits_a_statement():
    project = build_examox(buggy=False)
    assert DECLARED_NA in statement_numbers(project)
    # And the whole of Module 4 gets exactly one statement, not one per
    # 4.1/4.2/4.3 -- the source dossier files a single page.
    assert {n for n in statement_numbers(project) if n.startswith("4")} == {"4.0"}


def test_conditional_answered_no_emits_a_statement():
    project = build_examox(buggy=False)
    project.condition_answers = {CONDITIONAL: False}
    assert CONDITIONAL in statement_numbers(project)


def test_conditional_answered_yes_emits_nothing():
    """Answering "yes" means the section owes real content.

    A statement here would file a claim the applicant explicitly did not
    make -- the opposite error to omitting one, and the more damaging.
    """
    project = build_examox(buggy=False)
    project.condition_answers = {CONDITIONAL: True}
    assert CONDITIONAL not in statement_numbers(project)


def test_unanswered_conditional_emits_nothing():
    """Silence is not a "no". It is a WARNING (see R19 below)."""
    project = build_examox(buggy=False)
    project.condition_answers = {}
    assert CONDITIONAL not in statement_numbers(project)


def test_switching_submission_type_changes_which_leaves_are_required():
    """The seam the whole phase exists to create.

    A new chemical entity has no comparator product to be equivalent to, so
    it owes the nonclinical and clinical evidence a generic is excused --
    and the statements excusing it must disappear, not merely be joined by
    the real sections.
    """
    project = build_examox(buggy=False)
    generic = statement_numbers(project)

    project.submission_type = SubmissionType.NEW_CHEMICAL_ENTITY
    nce = statement_numbers(project)

    assert "4.0" in generic and "4.0" not in nce
    assert {"2.4", "2.5", "2.6", "2.7"} <= generic
    assert not {"2.4", "2.5", "2.6", "2.7"} & nce
    assert {"5.3.2", "5.3.7"} <= generic and not {"5.3.2", "5.3.7"} & nce

    required = NAFDAC_PROFILE.applicability_for(SubmissionType.NEW_CHEMICAL_ENTITY)
    assert required["4.0"].status is Applicability.REQUIRED


def test_eu_projects_emit_no_statements_because_nothing_is_declared():
    """An unmodelled region declares nothing, so it claims nothing.

    Empty means "not established", not "everything applies" -- the same
    convention EU_PROFILE's empty certificate list already follows. Guessing
    an exclusion on a regulator's behalf is the one outcome worse than not
    having the feature.
    """
    project = build_examox(buggy=False)
    project.region = Region.EU
    assert statement_numbers(project) == set()


# ---- what the statement actually says ---------------------------------------


def test_statement_document_names_its_section_and_cites_its_guideline():
    """The citation is the load-bearing sentence.

    An uncited "not applicable" is an absence with a covering note; a cited
    one is a scoped dossier. Rendering is checked here rather than in the
    package build so the assertion is about the words, not the PDF.
    """
    from docx import Document

    project = build_examox(buggy=False)
    storage = InMemoryStorageClient()
    result = render_section("4.0", project, storage=storage)

    import io

    document = Document(io.BytesIO(storage.get(result.storage_key)))
    text = "\n".join(p.text for p in document.paragraphs)

    assert "4.0" in text
    assert "not applicable" in text.lower()
    assert "NAFDAC guidelines for multisource" in text
    assert "NO GUIDELINE CITED" not in text


async def test_built_package_files_the_module_4_statement_in_m4(db_factory):
    """The definition of done, physically: `m4` is not an empty folder.

    Runs the real CTD builder (LibreOffice included) because the claim being
    made is about the shipped package, not about an intermediate list.
    """
    from app.ctd.build import build_ctd_package

    import io
    import zipfile

    from pypdf import PdfReader

    async with db_factory() as db:
        project = build_examox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        result = await build_ctd_package(db, project, storage=storage)
        paths = {f.path for f in result.manifest}
        zip_bytes = storage.get(result.storage_key)

    assert "m4/40-not-applicable/4.0.pdf" in paths
    assert "m2/24-nonclinical-overview/2.4.pdf" in paths
    assert "m5/53-clinical-study-reports/532-pk-using-human-biomaterials/5.3.2.pdf" in paths

    # READABLE, not merely present. A statement leaf that files an empty or
    # uncited page is the same failure as the empty folder it replaced, one
    # step further along -- so the assertion is on the words an assessor
    # would read, extracted from the PDF that actually ships.
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        pdf = zf.read("m4/40-not-applicable/4.0.pdf")
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    # PDF text extraction can re-wrap lines, so compare on unwrapped text --
    # the same handling tests/test_ctd_build.py already uses for the TOC.
    unwrapped = " ".join(text.split())
    assert "not applicable" in unwrapped.lower()
    assert "NAFDAC guidelines for multisource" in unwrapped


# ---- the rules --------------------------------------------------------------


def test_R19_warns_about_every_unanswered_condition():
    project = build_examox(buggy=False)
    project.condition_answers = {}

    findings = [f for f in run_all(project).findings if f.rule_id == "R19"]
    unanswered = {f.section for f in findings}

    conditional = {
        number
        for number, resolved in resolve_applicability(project).items()
        if resolved.section.status is Applicability.CONDITIONAL
    }
    assert unanswered == conditional
    # A WARNING, never a gate: an unrelated filing must not become
    # unshippable over a question that genuinely does not apply to it.
    assert run_all(project).is_exportable()


def test_R19_goes_quiet_once_a_condition_is_answered():
    project = build_examox(buggy=False)
    project.condition_answers = {CONDITIONAL: False}

    sections = {f.section for f in run_all(project).findings if f.rule_id == "R19"}
    assert CONDITIONAL not in sections


def test_R18_errors_when_an_excluded_section_nonetheless_has_content():
    """The dossier contradicting itself, which is worse than a gap."""
    project = build_examox(buggy=False)
    project.sections.append(
        Section(
            number=DECLARED_NA,
            title="Reports of studies pertinent to pharmacokinetics",
            narrative_text="A study was conducted in human liver microsomes.",
        )
    )

    report = run_all(project)
    findings = [f for f in report.findings if f.rule_id == "R18"]
    assert len(findings) == 1
    assert findings[0].section == DECLARED_NA
    assert not report.is_exportable()


def test_R18_is_silent_when_the_section_is_actually_owed():
    project = build_examox(buggy=False)
    project.submission_type = SubmissionType.NEW_CHEMICAL_ENTITY
    project.sections.append(
        Section(
            number=DECLARED_NA,
            title="Reports of studies pertinent to pharmacokinetics",
            narrative_text="A study was conducted in human liver microsomes.",
        )
    )

    assert not [f for f in run_all(project).findings if f.rule_id == "R18"]


# ---- the eCTD backbone ------------------------------------------------------


def test_statement_leaves_are_dtd_valid_in_the_ich_backbone():
    """Fourteen heading paths were typed from ich-ectd-3-2.dtd by hand.

    The whole point of registering statements as ordinary sections is that
    the backbone picks them up with no special case -- but only if every
    element name is right and every new parent's declared child order is
    known. Both failures are loud (`build_index_xml` raises on DTD
    validation), and neither is reachable from the EU-region eCTD build
    tests, since applicability is only modelled for NAFDAC. So they are
    exercised directly, all at once, deliberately in a scrambled order --
    m5-3 is the first parent in this project to hold seven sibling kinds,
    and the DTD's content models are ORDERED sequences.
    """
    from app.ectd.index_xml import build_index_xml
    from app.ectd.leaf import Leaf, leaf_id_for

    statements = sorted(
        (number for number, spec in SECTIONS.items() if spec.is_statement),
        reverse=True,
    )
    leaves = {
        number: Leaf(
            id=leaf_id_for(number, "0000"),
            title=f"{number} not applicable",
            href=f"{folder_for_section(number)}/{number}.pdf",
            checksum="a" * 32,
            operation="new",
        )
        for number in statements
    }

    xml_bytes = build_index_xml(leaves)

    assert b"m4-nonclinical-study-reports" in xml_bytes
    assert b"m5-3-7-case-report-forms-and-individual-patient-listings" in xml_bytes
    for number in statements:
        assert leaf_id_for(number, "0000").encode() in xml_bytes
