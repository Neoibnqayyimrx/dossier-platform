"""gap Phase 4b: the FDA regional backbone (`m1/us/us-regional.xml`).

Three layers, as for the EU:

- the pure builder, against FDA's real DTD (every build self-validates);
- FDA's CODES, against FDA's own published code lists -- the layer the
  EU never needed, because FDA's DTD accepts any string where a code goes;
- a real EXAMOX sequence built end to end as an FDA ANDA.

Validation of a built FDA package by the P10 mechanical checks (a
region-aware M02, and M13 for the codes) is gap Phase 4c.
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
    project = build_examox(buggy=False)
    project.region = Region.FDA
    project.product.registration_type = RegistrationType.NEW
    project.applicant.duns_number = "123456789"
    project.application_number = "212345"
    project.fda_application_type = FDAApplicationType.ANDA
    return project


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
