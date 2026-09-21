"""gap Phase 4b: the FDA regional backbone (`m1/us/us-regional.xml`).

Three layers, as for the EU:

- the pure builder, against FDA's real DTD (every build self-validates);
- FDA's CODES, against FDA's own published code lists -- the layer the
  EU never needed, because FDA's DTD accepts any string where a code goes;
- a real EXAMOX sequence built end to end as an FDA ANDA.

gap Phase 4c adds the fourth: built FDA packages judged by the P10
mechanical checks (M02 against FDA's DTD, M13 for FDA's codes), across a
three-sequence lifecycle.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from types import SimpleNamespace

import pytest
from lxml import etree
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ctd.region_profiles import FDA_PROFILE
from app.ectd import us_regional
from app.ectd.backbone import regional_backbone_for
from app.ectd.checksum import md5_hex
from app.ectd.errors import EctdNotSupportedError
from app.ectd.leaf import XLINK_NS, Leaf, leaf_id_for
from app.ectd.us_regional import build_us_regional_xml
from app.models import Base, FDAApplicationType, Region, RegistrationType, Sequence
from app.seed.examox import build_examox
from app.seed.fda import as_fda_original_application
from app.validation.engine import run_all

# ---- fixtures ---------------------------------------------------------------


def _project(**overrides) -> SimpleNamespace:
    """The minimum a us-regional.xml needs, as plain attributes."""
    applicant = SimpleNamespace(
        company_name="Exagon Pharmaceuticals Ltd",
        duns_number="123456789",
        contact_name="Aisha Bello",
        contact_phone="+234-800-000-0000",
        contact_email="regulatory@exagon.example",
    )
    project = SimpleNamespace(
        id=uuid.uuid4(),
        applicant=applicant,
        application_number="212345",
        fda_application_type=FDAApplicationType.ANDA,
        product=SimpleNamespace(brand_name="EXAMOX", registration_type=RegistrationType.NEW),
    )
    for name, value in overrides.items():
        target = applicant if hasattr(applicant, name) else project
        setattr(target, name, value)
    return project


def _leaf(key: str, href: str, sequence: str = "0001") -> Leaf:
    return Leaf(
        id=leaf_id_for(key, sequence), title=key, href=href, checksum="a" * 32, operation="new"
    )


_ALL_SLOTS = {
    "cover-letter": [_leaf("1.0", "m1/us/12-cover-letters/1.0.pdf")],
    "smpc": [_leaf("1.3.1", "m1/us/114-labeling/1.3.1.pdf")],
    "labelling": [_leaf("1.3.2", "m1/us/114-labeling/1.3.2.pdf")],
    "patient-information-leaflet": [_leaf("1.3.3", "m1/us/114-labeling/1.3.3.pdf")],
}


def _parse(xml_bytes: bytes) -> etree._Element:
    return etree.fromstring(xml_bytes)


# ---- FDA's codes, checked against FDA's own lists -----------------------------


def _code_list(name: str) -> dict[str, tuple[str, str]]:
    root = etree.parse(str(us_regional.CODE_LIST_DIR / f"{name}.xml")).getroot()
    return {
        el.get("code"): (el.get("display"), el.get("status")) for el in root.iter("code-display")
    }


@pytest.mark.parametrize("list_name", sorted(us_regional.CODES_IN_USE))
def test_every_code_the_builder_can_write_is_active_in_fda_s_own_list(list_name):
    """FDA Module 1 spec v2.6, section I: "only coded values with a status of
    'active' should be submitted". The DTD cannot check this -- it accepts
    any string -- so this test is what stands between a typo and a gateway
    rejection."""
    published = _code_list(list_name)
    for code in us_regional.CODES_IN_USE[list_name]:
        assert code in published, f"{code} is not in FDA's {list_name}.xml"
        assert published[code][1] == "active", f"{code} is {published[code][1]} in FDA's list"


def test_application_type_codes_mean_what_our_enum_says():
    """Present-and-active is not enough: fdaat1 and fdaat2 are both real
    codes, and swapping them files an ANDA as an NDA. So the MEANING is
    checked, against FDA's display names."""
    published = _code_list("application-type")
    expected = {
        FDAApplicationType.NDA: "New Drug Application (NDA)",
        FDAApplicationType.ANDA: "Abbreviated New Drug Application (ANDA)",
        FDAApplicationType.BLA: "Biologic License Application (BLA)",
    }
    assert set(us_regional.APPLICATION_TYPE_CODES) == set(FDAApplicationType)
    for application_type, code in us_regional.APPLICATION_TYPE_CODES.items():
        assert published[code][0] == expected[application_type]


def test_submission_codes_mean_what_the_builder_says():
    assert _code_list("submission-type")[us_regional.SUBMISSION_TYPE_ORIGINAL_APPLICATION][0] == (
        "Original Application"
    )
    sub_types = _code_list("submission-sub-type")
    assert sub_types[us_regional.SUBMISSION_SUB_TYPE_APPLICATION][0] == "Application"
    assert sub_types[us_regional.SUBMISSION_SUB_TYPE_AMENDMENT][0] == "Amendment"
    contact_types = _code_list("applicant-contact-type")
    assert contact_types[us_regional.APPLICANT_CONTACT_TYPE_REGULATORY][0] == "Regulatory Contact"
    phone_types = _code_list("telephone-number-type")
    assert phone_types[us_regional.TELEPHONE_NUMBER_TYPE_BUSINESS][0] == "Business Telephone Number"


def test_every_fda_profile_slot_has_a_heading_and_every_heading_a_slot():
    """A slot with no heading would put files in the package that the
    backbone never mentions; a heading with no slot is dead config."""
    slot_ids = {slot.slot_id for slot in FDA_PROFILE.module1_slots}
    assert slot_ids == set(us_regional.PLACED_SLOTS)


# ---- the builder ------------------------------------------------------------


def test_the_first_sequence_is_dtd_valid_and_carries_fda_s_fixed_header():
    xml_bytes = build_us_regional_xml(_project(), "0001", "0001", _ALL_SLOTS)
    head = xml_bytes.decode().splitlines()[:3]
    # FDA spec v2.6 section II: "The header ... is always the same."
    assert "standalone='no'" in head[0]
    assert head[1] == (
        "<!DOCTYPE fda-regional:fda-regional SYSTEM "
        '"https://www.accessdata.fda.gov/static/eCTD/us-regional-v3-3.dtd">'
    )
    assert "https://www.accessdata.fda.gov/static/eCTD/us-regional.xsl" in head[2]

    root = _parse(xml_bytes)
    assert root.get("dtd-version") == "3.3"
    assert root.findtext("admin/applicant-info/id") == "123456789"
    number = root.find(
        "admin/application-set/application/application-information/application-number"
    )
    assert (number.text, number.get("application-type")) == ("212345", "fdaat2")
    info = root.find("admin/application-set/application/submission-information")
    assert info.find("submission-id").get("submission-type") == "fdast1"
    assert info.findtext("submission-id") == "0001"
    assert info.find("sequence-number").get("submission-sub-type") == "fdasst3"


def test_module_1_is_filed_under_fda_s_headings_with_paths_from_m1_us():
    root = _parse(build_us_regional_xml(_project(), "0001", "0001", _ALL_SLOTS))
    m1 = root.find("m1-regional")
    cover = m1.find("m1-2-cover-letters/leaf")
    # FDA spec v2.6 section V: hrefs are relative to us-regional.xml.
    assert cover.get(f"{{{XLINK_NS}}}href") == "12-cover-letters/1.0.pdf"
    # FDA's conformance guide: a cover letter's leaf title carries the
    # sequence number, so one sequence's letter is told from the next's.
    assert cover.findtext("title") == "1.0 0001"

    draft = m1.find("m1-14-labeling/m1-14-1-draft-labeling")
    carton = draft.find("m1-14-1-1-draft-carton-and-container-labels")
    text = draft.find("m1-14-1-3-draft-labeling-text")
    assert [leaf.findtext("title") for leaf in carton] == ["1.3.2"]
    assert [leaf.findtext("title") for leaf in text] == ["1.3.1", "1.3.3"]
    # One m1-14-labeling, not one per slot: two paths share it.
    assert len(m1.findall("m1-14-labeling")) == 1


def test_an_amendment_names_the_original_application_as_its_regulatory_activity():
    """FDA spec v2.6 III.B.3: submission-id is the FIRST sequence of the
    regulatory activity; sequence-number is this one. That pairing is how
    FDA's review tool puts an amendment under the application it amends."""
    root = _parse(build_us_regional_xml(_project(), "0003", "0001", {}, "response"))
    info = root.find("admin/application-set/application/submission-information")
    assert info.findtext("submission-id") == "0001"
    assert info.findtext("sequence-number") == "0003"
    assert info.find("sequence-number").get("submission-sub-type") == "fdasst4"
    assert "amendment" in root.findtext("admin/applicant-info/submission-description")


def test_a_sequence_that_changes_nothing_in_module_1_has_no_m1_regional():
    """ "Empty section headings should not be included" (spec v2.6), and the
    DTD makes m1-regional itself optional."""
    root = _parse(build_us_regional_xml(_project(), "0002", "0001", {}, "response"))
    assert root.find("m1-regional") is None


def test_a_second_initial_sequence_is_refused_with_the_value_to_use():
    """Every sequence defaults to `initial`, so this is the mistake a filer
    will actually make -- and FDA allows one `application` per activity."""
    with pytest.raises(EctdNotSupportedError, match="'response'"):
        build_us_regional_xml(_project(), "0002", "0001", {}, "initial")


@pytest.mark.parametrize("unit_type", ["closing", "consolidating", "corrigendum", "reformat"])
def test_eu_transaction_types_with_no_fda_counterpart_are_refused(unit_type):
    with pytest.raises(EctdNotSupportedError, match="no FDA equivalent"):
        build_us_regional_xml(_project(), "0002", "0001", {}, unit_type)


@pytest.mark.parametrize(
    ("registration_type", "phrase"),
    [(RegistrationType.RENEWAL, "no renewal"), (RegistrationType.VARIATION, "supplement")],
)
def test_renewals_and_variations_are_refused_rather_than_mislabelled(registration_type, phrase):
    project = _project()
    project.product.registration_type = registration_type
    with pytest.raises(EctdNotSupportedError, match=phrase):
        build_us_regional_xml(project, "0001", "0001", _ALL_SLOTS)


def test_missing_admin_data_is_refused_rather_than_written_blank():
    """FDA's DTD accepts an empty <id/>. So the builder refuses -- even if
    rule R34 was overridden -- rather than publish a backbone with no
    D-U-N-S number in it."""
    with pytest.raises(EctdNotSupportedError, match="D-U-N-S"):
        build_us_regional_xml(_project(duns_number=None), "0001", "0001", _ALL_SLOTS)


def test_a_slot_with_no_fda_heading_is_a_loud_config_error():
    with pytest.raises(ValueError, match="No FDA Module 1 heading"):
        build_us_regional_xml(
            _project(), "0001", "0001", {"certificates": [_leaf("c", "m1/us/c.pdf")]}
        )


def test_nafdac_is_told_it_takes_ctd_not_that_ectd_is_unfinished():
    with pytest.raises(EctdNotSupportedError, match="NAFDAC takes CTD, not eCTD"):
        regional_backbone_for(Region.NAFDAC)


# ---- rules R34 / R35 ----------------------------------------------------------


def _fda_examox():
    # buggy=False: EXAMOX's default build carries planted copy-paste defects
    # (the rule-engine fixtures), which would block assembly for reasons
    # that have nothing to do with FDA.
    return as_fda_original_application(build_examox(buggy=False))


def _findings(project, rule_id: str):
    return [f for f in run_all(project).findings if f.rule_id == rule_id]


def test_a_complete_fda_project_raises_neither_r34_nor_r35():
    project = _fda_examox()
    assert _findings(project, "R34") == []
    assert _findings(project, "R35") == []


def test_r34_names_each_missing_identifier_and_fda_s_duns_allowance():
    project = _fda_examox()
    project.application_number = None
    project.applicant.duns_number = None
    messages = [f.message for f in _findings(project, "R34")]
    assert len(messages) == 2
    assert any("application number" in m for m in messages)
    assert any("D-U-N-S" in m and "999999999" in m for m in messages)
    assert run_all(project).errors()


def test_r34_rejects_an_application_number_written_the_way_people_say_it():
    project = _fda_examox()
    project.application_number = "ANDA 212345"
    (finding,) = _findings(project, "R34")
    assert "six digits" in finding.message


def test_r35_puts_the_builder_s_own_refusal_on_the_readiness_report():
    project = _fda_examox()
    project.product.registration_type = RegistrationType.RENEWAL
    (finding,) = _findings(project, "R35")
    assert finding.message == us_regional.unsupported_reason(project)


def test_the_fda_rules_do_not_apply_to_other_regions():
    project = _fda_examox()
    project.region = Region.EU
    project.application_number = None
    assert _findings(project, "R34") == []


# ---- sequence numbering -------------------------------------------------------


async def _create_project(auth_client, region: str) -> str:
    product = (
        await auth_client.post(
            "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
        )
    ).json()
    project = await auth_client.post(
        "/projects", json={"name": "EXAMOX", "product_id": product["id"], "region": region}
    )
    assert project.status_code == 201, project.text
    return project.json()["id"]


@pytest.mark.parametrize(("region", "first"), [("FDA", "0001"), ("EU", "0000"), ("NAFDAC", "0000")])
async def test_the_first_sequence_number_is_the_region_s(auth_client, region, first):
    """FDA's conformance guide: "begin with sequence number 0001"."""
    project_id = await _create_project(auth_client, region)
    numbers = [
        (await auth_client.post(f"/projects/{project_id}/sequences", json={})).json()["number"]
        for _ in range(2)
    ]
    assert numbers == [first, f"{int(first) + 1:04d}"]


async def test_the_fda_identifiers_round_trip_through_the_api(auth_client):
    applicant = await auth_client.post(
        "/applicants", json={"company_name": "Exagon", "duns_number": "123456789"}
    )
    assert applicant.status_code == 201, applicant.text
    assert applicant.json()["duns_number"] == "123456789"

    project_id = await _create_project(auth_client, "FDA")
    patched = await auth_client.patch(
        f"/projects/{project_id}",
        json={"application_number": "212345", "fda_application_type": "anda"},
    )
    assert patched.status_code == 200, patched.text
    assert (patched.json()["application_number"], patched.json()["fda_application_type"]) == (
        "212345",
        "anda",
    )


async def test_a_duns_number_that_is_not_nine_digits_is_refused_at_the_door(auth_client):
    resp = await auth_client.post(
        "/applicants", json={"company_name": "Exagon", "duns_number": "12-345-6789"}
    )
    assert resp.status_code == 422


# ---- a real sequence, end to end ----------------------------------------------


@pytest.fixture
async def db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def test_nafdac_is_refused_before_anything_is_rendered(db_factory, monkeypatch):
    """The refusal must not cost a package's worth of LibreOffice runs."""
    from app.ectd import build

    async def must_not_assemble(*args, **kwargs):
        raise AssertionError("assembly ran for a region that has no eCTD backbone")

    monkeypatch.setattr(build, "assemble_project", must_not_assemble)
    async with db_factory() as db:
        project = build_examox()
        db.add(project)
        await db.commit()
        sequence = Sequence(project_id=project.id, number="0000")
        db.add(sequence)
        await db.commit()
        with pytest.raises(EctdNotSupportedError, match="NAFDAC takes CTD"):
            await build.build_ectd_sequence(db, project, sequence)


async def test_an_fda_anda_builds_end_to_end(db_factory):
    from app.core.storage import InMemoryStorageClient
    from app.ectd.build import build_ectd_sequence

    async with db_factory() as db:
        project = _fda_examox()
        db.add(project)
        await db.commit()
        sequence = Sequence(project_id=project.id, number="0001")
        db.add(sequence)
        await db.commit()

        storage = InMemoryStorageClient()
        result = await build_ectd_sequence(db, project, sequence, storage=storage)
        with zipfile.ZipFile(io.BytesIO(storage.get(result.storage_key))) as zf:
            files = {name: zf.read(name) for name in zf.namelist()}

    names = set(files)
    assert "0001/m1/us/us-regional.xml" in names
    assert {"0001/util/dtd/us-regional-v3-3.dtd", "0001/util/style/us-regional.xsl"} <= names
    # Nothing of the EU's, and nothing FDA's Module 1 has no heading for.
    assert not any("/m1/eu/" in n or "eu-regional" in n for n in names)
    assert not any("certificates" in n or "declarations" in n for n in names)
    assert not any(n.endswith("/1.2.2.pdf") for n in names)

    index = etree.fromstring(files["0001/index.xml"])
    (m1_leaf,) = index.findall("m1-administrative-information-and-prescribing-information/leaf")
    assert m1_leaf.get(f"{{{XLINK_NS}}}href") == "m1/us/us-regional.xml"
    assert m1_leaf.get("checksum") == md5_hex(files["0001/m1/us/us-regional.xml"])

    # Every Module 1 leaf resolves from m1/us/ to a file that shipped, and
    # its checksum is that file's.
    regional = etree.fromstring(files["0001/m1/us/us-regional.xml"])
    leaves = list(regional.iter("leaf"))
    assert {leaf.getparent().tag for leaf in leaves} == {
        "m1-2-cover-letters",
        "m1-14-1-1-draft-carton-and-container-labels",
        "m1-14-1-3-draft-labeling-text",
    }
    for leaf in leaves:
        path = f"0001/m1/us/{leaf.get(f'{{{XLINK_NS}}}href')}"
        assert md5_hex(files[path]) == leaf.get("checksum"), path


async def test_an_fda_amendment_is_created_as_one_from_the_api(auth_client):
    """gap Phase 4c: the transaction type is stated when the sequence is
    created. Before, it could only be PATCHed afterwards, so the UI's
    create-then-build always produced an `initial` -- which FDA refuses for
    anything after the original application."""
    project_id = await _create_project(auth_client, "FDA")
    first = (await auth_client.post(f"/projects/{project_id}/sequences", json={})).json()
    second = await auth_client.post(
        f"/projects/{project_id}/sequences", json={"submission_unit_type": "response"}
    )
    assert second.status_code == 201, second.text
    assert (first["submission_unit_type"], second.json()["submission_unit_type"]) == (
        "initial",
        "response",
    )


async def test_three_fda_sequences_pass_every_mechanical_check(db_factory):
    """The FDA lifecycle, end to end, judged by the P10 validator.

    0001  the original application.
    0002  an amendment renaming the applicant. The name prints on the
          SmPC, labels and leaflet as marketing authorisation holder, so all
          three are REPLACED in us-regional.xml, pointing back into 0001's
          us-regional.xml from three folders down -- and in the Module 2
          introduction, replaced in index.xml. One sequence, both backbones.
    0003  an amendment changing only Module 3: a drug-substance test method,
          replaced in index.xml, pointing back into 0001's index.xml.

    Both amendments name 0001 as their regulatory activity (submission-id)
    and themselves as the sequence. Every sequence is run through all of
    M01-M13 against the sequences before it.
    """
    from app.core.storage import InMemoryStorageClient
    from app.ectd.build import build_ectd_sequence
    from app.ectd.validate import run_mechanical_checks
    from app.models import SubmissionUnitType
    from app.templating.instances import expand_sections
    from app.validation.engine import Severity

    async with db_factory() as db:
        project = _fda_examox()
        db.add(project)
        await db.commit()
        storage = InMemoryStorageClient()
        expected = {i.key for i in expand_sections(project)}

        def rename_applicant():
            project.applicant.company_name = "Exagon Pharmaceuticals (US) Inc."

        def change_test_method():
            project.product.apis[0].specification[0].method = "Visual, USP monograph"

        bundles: dict[str, dict[str, bytes]] = {}
        operations: dict[str, dict[str, str]] = {}
        for number, unit_type, change in (
            ("0001", SubmissionUnitType.INITIAL, None),
            ("0002", SubmissionUnitType.RESPONSE, rename_applicant),
            ("0003", SubmissionUnitType.RESPONSE, change_test_method),
        ):
            if change:
                change()
            sequence = Sequence(
                project_id=project.id, number=number, submission_unit_type=unit_type
            )
            db.add(sequence)
            await db.commit()
            result = await build_ectd_sequence(db, project, sequence, storage=storage)
            with zipfile.ZipFile(io.BytesIO(storage.get(result.storage_key))) as zf:
                bundles[number] = {name: zf.read(name) for name in zf.namelist()}
            operations[number] = result.operations

            findings = run_mechanical_checks(
                number,
                bundles[number],
                prior_files={n: b for n, b in bundles.items() if n < number},
                live_section_keys=set(expected),
                expected_section_keys=expected,
            )
            errors = [f for f in findings if f.severity is Severity.ERROR]
            assert errors == [], (number, [f"{f.rule_id}: {f.message}" for f in errors])

    # 0002 replaced the three labeling documents (and 2.2); 0003 touched no
    # Module 1 document at all.
    assert set(operations["0002"].values()) == {"replace"}
    assert {"1.3.1", "1.3.2", "1.3.3"} <= set(operations["0002"]), operations["0002"]
    assert operations["0003"] and set(operations["0003"].values()) == {"replace"}
    assert not any(key.startswith("1.") for key in operations["0003"]), operations["0003"]

    amendment = etree.fromstring(bundles["0002"]["0002/m1/us/us-regional.xml"])
    info = amendment.find("admin/application-set/application/submission-information")
    assert (info.findtext("submission-id"), info.findtext("sequence-number")) == ("0001", "0002")
    assert info.find("sequence-number").get("submission-sub-type") == "fdasst4"
    modified = {leaf.get("modified-file") for leaf in amendment.iter("leaf")}
    assert modified and all(m.startswith("../../../0001/m1/us/us-regional.xml#") for m in modified)

    index = bundles["0003"]["0003/index.xml"]
    assert b'modified-file="../0001/index.xml#ID-3-2-S-4' in index
    # A sequence that changes nothing in Module 1 still has its us-regional.xml
    # (the admin block says what the sequence IS), just no m1-regional.
    third = etree.fromstring(bundles["0003"]["0003/m1/us/us-regional.xml"])
    assert third.find("m1-regional") is None


async def test_the_consolidated_report_on_an_fda_sequence_is_exportable(db_factory):
    """The path the API takes (POST /validate/ectd): data rules, mechanical
    checks and the external-validator placeholder, merged. An FDA sequence
    built from clean data must come out exportable -- R34/R35 silent, M02
    and M13 silent -- with the honest EXT00 advisory that no agency
    validator ran."""
    from app.core.storage import InMemoryStorageClient
    from app.ectd.build import build_ectd_sequence
    from app.ectd.report import validate_ectd_sequence

    async with db_factory() as db:
        project = _fda_examox()
        db.add(project)
        await db.commit()
        sequence = Sequence(project_id=project.id, number="0001")
        db.add(sequence)
        await db.commit()
        storage = InMemoryStorageClient()
        await build_ectd_sequence(db, project, sequence, storage=storage)
        report = await validate_ectd_sequence(
            db, project, sequence, storage=storage, run_ai_review=False
        )

    assert report.is_exportable(), [f"{f.rule_id}: {f.message}" for f in report.errors()]
    rule_ids = {f.rule_id for f in report.findings}
    assert not rule_ids & {"R34", "R35", "M02", "M13"}
    assert "EXT00" in rule_ids
