"""Tests: the SmPC, the label and the leaflet from one dataset (P23).

The phase's claim is that the most commonly raised deficiency in this part
of a dossier -- three product-information documents that disagree about
shelf life, storage or pack size -- is a bookkeeping failure, and that a
platform rendering all three from one dataset makes it unproducible.

These tests pin that claim from both ends:

  * a shelf-life change in the STABILITY data reaches all three documents,
    and the three cannot be made to disagree even deliberately;
  * an excipient in the batch formula but absent from the leaflet is
    caught, and so is the reverse;
  * a storage statement warmer than the study that supports it is caught,
    which is the climatic-zone defect a filing assembled from a European
    parent dossier arrives with;
  * the API refuses to accept a derived field rather than silently
    dropping it;
  * leaflet prose is judged in a different register from SmPC prose.
"""

from __future__ import annotations

import io

from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.storage import InMemoryStorageClient
from app.ctd.region_profiles import EU_PROFILE, NAFDAC_PROFILE
from app.models import (
    AdverseEventFrequency,
    Base,
    BatchFormulaLine,
    Excipient,
    NarrativeRegister,
    ProductInformation,
    Section,
    StabilityStudyType,
)
from app.narrative.guardrails import check_patient_register
import app.validation.rules  # noqa: F401  registers rules
from app.seed.ampiclox import build_ampiclox
from app.seed.examox import build_examox
from app.templating.context import build_context
from app.templating import product_information
from app.templating.instances import expand_sections
from app.templating.product_information import shared_values
from app.templating.registry import SECTIONS
from app.templating.render import render_section
from app.validation.engine import Severity, run_all

DOCUMENTS = ("1.3.1", "1.3.2", "1.3.3")


def _load(builder, **kwargs):
    """Build a seeded project and persist it to a throwaway SQLite database.

    WHY the session is pinned to the returned object: `session.refresh()`
    expires EVERY attribute, relationships included, so a rule that walks
    `project.declarations` later triggers a lazy load -- and a lazy load
    needs the Session, which nothing else here holds a strong reference to.
    When garbage collection reached it first, the run failed with a
    DetachedInstanceError raised inside rule R15, in a DIFFERENT test from
    the one that had built the project, roughly one run in three.

    The same helper is copied into eleven other test files (grep
    `session.refresh(project)`); they carry the same latent hazard and are
    left alone here because none of them has been seen to fail. This is
    where it was reproduced, so this is where it is fixed.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    project = builder(**kwargs)
    session.add(project)
    session.commit()
    session.refresh(project)
    project._test_session = session
    return project


def _render(project, number):
    storage = InMemoryStorageClient()
    result = render_section(number, project, storage=storage)
    return Document(io.BytesIO(storage.get(result.storage_key)))


def _text(doc) -> str:
    paragraphs = "\n".join(p.text for p in doc.paragraphs)
    cells = "\n".join(cell.text for table in doc.tables for row in table.rows for cell in row.cells)
    return f"{paragraphs}\n{cells}"


def _findings(project, rule_id):
    return [f for f in run_all(project).findings if f.rule_id == rule_id]


# ---- the derivation, which is the whole phase -------------------------------


def test_a_shelf_life_change_reaches_all_three_documents():
    """THE test for this phase, and the one the prompt asks for by name.

    Nothing here touches the SmPC, the label or the leaflet. It changes the
    product's claim -- the single place a shelf life is stored -- and
    asserts that all three documents followed. In a dossier where each
    document held its own copy, two of them would still say 24 months, and
    that is precisely the deficiency this phase removes.
    """
    project = _load(build_examox, buggy=False)
    before = {number: _text(_render(project, number)) for number in DOCUMENTS}
    for text in before.values():
        assert "24 months" in text

    project.product.shelf_life_months = 36
    after = {number: _text(_render(project, number)) for number in DOCUMENTS}
    for number, text in after.items():
        assert "36 months" in text, f"{number} did not follow the change"
        assert "24 months" not in text, f"{number} still carries the old shelf life"


def test_none_of_the_three_can_be_made_to_disagree():
    """The other half of the same claim: there is no way to make them
    differ, because there is only one expression of each shared value.

    Every shared field is compared across the three rendered contexts. The
    assertion is not that they happen to match today -- it is that the
    three read one function, so matching is structural. Rule R31 holds the
    same line in a running system; this holds it in CI.
    """
    project = _load(build_examox, buggy=False)
    shared = {number: build_context(number, project)["shared"] for number in DOCUMENTS}

    fields = set(shared["1.3.1"])
    assert fields, "the SmPC context carries no shared values at all"
    for field in fields:
        values = {shared[number][field] for number in DOCUMENTS}
        assert len(values) == 1, f"{field} differs across the documents: {values}"

    assert not [f for f in run_all(project).findings if f.rule_id == "R31"]


def test_r31_fires_when_a_second_copy_of_a_value_is_introduced(monkeypatch):
    """The tripwire, tripped.

    R31 cannot fire while the derivation holds, so this forces the exact
    regression it is waiting for -- a document formatting a shared value
    for itself instead of reading `shared` -- and asserts the rule catches
    it. A guard nobody has ever seen fire is a guard nobody trusts.

    WHY pytest's `monkeypatch` rather than saving and restoring the
    attribute by hand: this test deliberately breaks a module every other
    test in this file renders through, and a hand-written `finally` only
    covers the paths its author thought of. `monkeypatch` restores on any
    exit, including a collection-time error -- and a leak here would not
    fail loudly, it would make `test_none_of_the_three_can_be_made_to_
    disagree` fail somewhere else in the run.
    """
    project = _load(build_examox, buggy=False)
    real_label_context = product_information.label_context

    def divergent_label_context(section, project):
        context = real_label_context(section, project)
        context["shared"] = {**context["shared"], "shelf_life": "36 months"}
        return context

    monkeypatch.setattr(product_information, "label_context", divergent_label_context)
    findings = _findings(project, "R31")

    assert findings, "R31 did not notice the label printing a different shelf life"
    finding = findings[0]
    assert finding.severity is Severity.ERROR
    # Names BOTH values and BOTH locations, which is what the prompt asks
    # a divergence finding to do.
    assert "24 months" in finding.message and "36 months" in finding.message
    assert "1.3.1" in finding.message and "1.3.2" in finding.message


def test_every_shared_value_says_where_it_comes_from():
    """A read-only field with no provenance teaches nothing. The wizard and
    the comparison screen both print `source`, so it has to be there for
    every value, not most of them."""
    project = _load(build_examox, buggy=False)
    for value in shared_values(project.product):
        assert value.source, f"{value.field} is derived from nowhere in particular"
        assert value.label


def test_the_shelf_life_provenance_names_what_the_data_supports():
    """The provenance string is where the filer sees the claim and the
    evidence side by side -- the same pairing rule R05 gates on."""
    project = _load(build_examox, buggy=False)
    shelf_life = next(v for v in shared_values(project.product) if v.field == "shelf_life")

    assert shelf_life.value == "24 months"
    assert "supports 24 months" in shelf_life.source
    assert "R05" in shelf_life.source


# ---- the cross-document rules -----------------------------------------------


def test_r28_catches_an_excipient_in_the_batch_formula_but_not_the_leaflet():
    """The prompt's second named test, and the seeded AMPICLOX defect.

    A glidant added to the batch formula and never added to the excipient
    rows is manufactured into every capsule and named in neither SmPC 6.1
    nor the leaflet. A patient with an intolerance reads the leaflet.
    """
    project = _load(build_ampiclox, buggy=True)
    findings = _findings(project, "R28")

    assert findings, "an undeclared batch formula component was not caught"
    finding = next(f for f in findings if "Colloidal Silicon Dioxide" in f.message)
    assert finding.severity is Severity.ERROR
    # Names both locations, so a filer knows which of the two tables to fix.
    assert "3.2.P.3.2" in finding.message
    assert "1.3.1/1.3.3" in finding.message
    assert not run_all(project).is_exportable()


def test_r28_catches_the_reverse_too():
    """An excipient the leaflet lists that is not actually manufactured in
    is the same defect from the other side, and just as misleading."""
    project = _load(build_examox, buggy=False)
    assert not _findings(project, "R28")

    project.product.excipients.append(Excipient(name="Lactose Monohydrate"))
    finding = next(f for f in _findings(project, "R28") if "Lactose" in f.message)

    assert finding.severity is Severity.ERROR
    assert "no line in the batch formula" in finding.message


def test_r28_does_not_report_a_difference_of_case_or_spacing():
    """Two tables typed by two people at two times. "Magnesium Stearate"
    and "magnesium  stearate" are the same material, and a rule that says
    otherwise is a rule people learn to ignore."""
    project = _load(build_examox, buggy=False)
    for line in project.product.batch_formula:
        line.component = line.component.upper().replace(" ", "  ")

    assert not _findings(project, "R28")


def test_r29_catches_a_label_warmer_than_the_study_that_supports_it():
    """The climatic-zone defect.

    Zone II tests at 25 C; Zone IVb (Nigeria) at 30 C. A dossier assembled
    from a European parent filing arrives with 25 C data and a label
    rewritten for the Nigerian market, and the two now disagree by five
    degrees nobody typed on purpose.
    """
    project = _load(build_examox, buggy=False)
    assert not _findings(project, "R29")

    for study in project.product.stability:
        if study.study_type is StabilityStudyType.LONG_TERM:
            study.condition = "25C/60%RH"

    finding = _findings(project, "R29")[0]
    assert finding.severity is Severity.ERROR
    assert "30 C" in finding.message and "25 C" in finding.message
    assert "3.2.P.8.3" in finding.message


def test_r29_is_silent_when_there_is_no_temperature_to_compare():
    """A storage statement with no number in it is not a divergence. The
    rule parses free text on both sides, so it has to be honest about what
    it cannot read rather than inventing a finding."""
    project = _load(build_examox, buggy=False)
    project.product.storage_condition = "Protect from light and moisture."

    assert not _findings(project, "R29")


def test_r30_blocks_on_the_three_sections_that_are_the_application():
    """4.1, 4.2 and 4.3 are what is being applied for. Without them there
    is a well-formed SmPC with nothing in it, which is the failure that
    derivation cannot cover -- these sections exist nowhere else."""
    project = _load(build_examox, buggy=False)
    assert not [f for f in _findings(project, "R30") if f.severity is Severity.ERROR]

    project.product.product_information.therapeutic_indications = None
    project.product.product_information.contraindications = []
    errors = [f for f in _findings(project, "R30") if f.severity is Severity.ERROR]

    assert {"4.1" in f.message for f in errors} == {True} or any("4.1" in f.message for f in errors)
    assert any("4.3" in f.message for f in errors)
    assert not run_all(project).is_exportable()


def test_r30_only_warns_about_a_section_that_can_legitimately_be_short():
    """ "No interactions are known" and "nobody filled this in" are
    different statements, and only one is a filing -- so the platform asks
    rather than blocks."""
    project = _load(build_examox, buggy=False)
    project.product.product_information.interactions = None
    finding = next(f for f in _findings(project, "R30") if "4.5" in f.message)

    assert finding.severity is Severity.WARNING


def test_r30_says_so_when_there_is_no_product_information_at_all():
    project = _load(build_examox, buggy=False)
    project.product.product_information = None
    findings = _findings(project, "R30")

    assert len(findings) == 1
    assert findings[0].severity is Severity.ERROR
    assert "1.3.1" in findings[0].message and "1.3.3" in findings[0].message


def test_r32_flags_a_contraindication_the_leaflet_prose_lost():
    """The list is printed either way -- that guarantee is in the template.
    What this checks is the prose a patient actually reads."""
    project = _load(build_examox, buggy=False)
    project.sections.append(
        Section(
            number="1.3.3",
            title="Patient Information Leaflet",
            narrative_text=(
                "Do not take this medicine if you are allergic to penicillins. "
                "Tell your doctor about any other medicines you take."
            ),
        )
    )
    findings = _findings(project, "R32")

    # The jaundice/liver contraindication is nowhere in that prose.
    assert any("jaundice" in f.message for f in findings)
    assert all(f.severity is Severity.WARNING for f in findings)
    # And the one the prose DOES carry is not reported.
    assert not any("allergic to penicillins" in f.message for f in findings)


def test_r32_is_silent_before_any_leaflet_prose_exists():
    project = _load(build_examox, buggy=False)
    assert not _findings(project, "R32")


# ---- the leaflet register ---------------------------------------------------


def test_the_leaflet_is_declared_a_different_kind_of_narrative_slot():
    """Not the same slot with a different prompt. The register is a
    property of the section, so it survives a model that answered in the
    wrong voice."""
    assert SECTIONS["1.3.3"].narrative_register is NarrativeRegister.PATIENT
    assert SECTIONS["1.3.1"].narrative_register is NarrativeRegister.REGULATORY
    assert SECTIONS["1.3.2"].narrative_slots == []


def test_the_patient_guardrail_names_the_term_and_the_plain_alternative():
    """A readability score says "grade 14". This says which word to change,
    which is the difference between a measurement and a correction."""
    warnings = check_patient_register(
        "This medicine is contraindicated in patients with hepatic impairment."
    )

    assert any("'contraindicated'" in w and "'must not be used'" in w for w in warnings)
    assert any("'hepatic'" in w and "'liver'" in w for w in warnings)


def test_the_patient_guardrail_accepts_a_leaflet_that_reads_like_one():
    assert (
        check_patient_register(
            "Do not take this medicine if you have ever had an allergic reaction to "
            "penicillin. Tell your doctor if you have liver problems."
        )
        == []
    )


def test_the_same_prose_is_fine_in_an_smpc_and_flagged_in_a_leaflet():
    """The point of a register: this sentence is CORRECT regulatory
    writing. It is only a defect because of who is reading it."""
    smpc_sentence = "Administration is contraindicated in severe hepatic impairment."

    assert check_patient_register(smpc_sentence)
    # And nothing runs it against an SmPC slot: generate_narrative only
    # applies the register check when the section declares PATIENT.
    assert SECTIONS["1.3.1"].narrative_register is not NarrativeRegister.PATIENT


def test_r33_gates_approved_leaflet_text_at_export():
    """A guardrail warning at generation time is advice. The same finding
    on the readiness report is what a filer has to look at before
    building."""
    project = _load(build_examox, buggy=False)
    project.sections.append(
        Section(
            number="1.3.3",
            title="Patient Information Leaflet",
            narrative_text=(
                "This medicine is contraindicated in patients with renal impairment "
                "and you should tell your doctor."
            ),
        )
    )
    findings = _findings(project, "R33")

    assert any("contraindicated" in f.message for f in findings)
    assert all(f.severity is Severity.WARNING for f in findings)
    # A readability failure is not a false statement, so it must not block.
    assert "R33" not in {f.rule_id for f in run_all(project).errors()}


# ---- what the three documents actually say ----------------------------------


def test_the_label_is_generated_with_no_drafted_text_on_it():
    project = _load(build_examox, buggy=False)
    text = _text(_render(project, "1.3.2"))

    assert "AI DRAFT PENDING" not in text
    assert "EXAMOX" in text
    assert "Store below 30 C" in text


def test_the_label_leaves_the_per_batch_fields_to_the_packing_line():
    """Batch number and expiry are applied at packing. A dossier that
    filled them in would file one batch's label as the artwork for all of
    them."""
    text = _text(_render(_load(build_examox, buggy=False), "1.3.2"))

    assert "Batch number" in text and "Expiry date" in text
    assert "overprinted" in text.lower() or "Applied at packing" in text


def test_the_smpc_carries_its_own_section_numbers():
    """An assessor's query arrives as "6.4 contradicts 3.2.P.8". A document
    that does not carry those numbers cannot be answered against."""
    text = _text(_render(_load(build_examox, buggy=False), "1.3.1"))

    for heading in ("4.1", "4.3", "5.1", "6.1", "6.3", "6.4", "6.5"):
        assert heading in text, f"SmPC section {heading} is missing"


def test_the_leaflet_prints_the_contraindication_list_even_before_the_prose():
    """The list is the guarantee and the prose is the readability. A
    leaflet whose narrative is still a draft must already carry every
    contraindication."""
    text = _text(_render(_load(build_examox, buggy=False), "1.3.3"))

    assert "AI DRAFT PENDING" in text  # nothing generated yet
    assert "allergic to penicillins" in text
    assert "jaundice" in text


def test_undesirable_effects_are_ordered_by_frequency_band_in_both_documents():
    """Both documents print 4.8 grouped by band, most common first -- which
    is only possible because the band is a controlled value and not a
    heading someone typed."""
    project = _load(build_examox, buggy=False)
    for number in ("1.3.1", "1.3.3"):
        rows = build_context(number, project)["undesirable_effects"]
        frequencies = [row["frequency"] for row in rows]
        order = [f.value for f in AdverseEventFrequency]
        assert frequencies == sorted(frequencies, key=order.index)
        assert frequencies[0] == AdverseEventFrequency.COMMON.value


def test_a_product_with_no_smpc_content_still_renders_all_three():
    """A gap has to show up in the package under review, not as a crash at
    build time -- the same call `folder_for_section` makes in the other
    direction. R30 is what says the section is empty."""
    project = _load(build_examox, buggy=False)
    project.product.product_information = None

    for number in DOCUMENTS:
        assert "NOT YET ON FILE" in _text(_render(project, number)) or number == "1.3.2"


# ---- placement --------------------------------------------------------------


def test_all_three_leaves_have_somewhere_to_be_filed_in_both_regions():
    """A registered section with no home is a document that cannot be
    built. Both profiles, because unlike 1.4.1 these three are not
    conditional -- they are emitted for every project, so an EU project
    would raise at build time if only NAFDAC had folders."""
    for profile in (NAFDAC_PROFILE, EU_PROFILE):
        placed = {slot.section_number: slot.folder for slot in profile.module1_slots}
        for number in DOCUMENTS:
            assert number in placed, f"{number} has no Module 1 slot for {profile.region}"


def test_the_three_documents_are_emitted_for_every_project():
    project = _load(build_examox, buggy=False)
    keys = {instance.key for instance in expand_sections(project)}

    assert set(DOCUMENTS) <= keys


def test_the_eu_backbone_files_each_document_under_its_own_pi_doc_type():
    """eu-regional.dtd declares `m1-3-1-spc-label-pl (pi-doc+)` with
    pi-doc's `type` #REQUIRED from (spc|annex2|outer|interpack|impack|
    other|pl|combined) -- the EU spec names these three documents itself
    and insists you say which is which, because an assessor's software
    routes on that attribute.
    """
    from app.ectd.regional import _PI_DOC_TYPE_BY_SLOT

    slots = {slot.section_number: slot.slot_id for slot in EU_PROFILE.module1_slots}
    assert _PI_DOC_TYPE_BY_SLOT[slots["1.3.1"]] == "spc"
    assert _PI_DOC_TYPE_BY_SLOT[slots["1.3.2"]] == "outer"
    assert _PI_DOC_TYPE_BY_SLOT[slots["1.3.3"]] == "pl"


def test_the_regional_backbone_actually_carries_the_three_pi_docs():
    """Placement without backbone entries would be the exact "looks
    complete, is not" failure this platform exists to prevent: three files
    in the package that the regional XML never mentions.

    So this builds the real XML and reads it back. It also pins the CHILD
    ORDER -- the DTD declares m1-eu's children in a fixed sequence and lxml
    appends in call order, so a pi-doc attached before m1-2-form fails
    validation with a message about content models rather than about order.
    """
    from lxml import etree

    from app.ectd.leaf import Leaf
    from app.ectd.regional import build_regional_xml
    from app.models import Region

    project = build_examox(buggy=False)
    project.region = Region.EU

    def leaf(key: str, title: str) -> Leaf:
        return Leaf(
            id=f"ID-{key}",
            title=title,
            href=f"m1/eu/13-product-information/{key}.pdf",
            checksum="0" * 32,
            operation="new",
            modified_file=None,
        )

    # `related-sequence+` is #REQUIRED by the envelope's own content model,
    # so the sequence itself is passed -- an empty list fails DTD
    # validation on the ENVELOPE and tells you nothing about m1-3-pi.
    xml = build_regional_xml(
        project,
        "0000",
        ["0000"],
        {
            "cover-letter": [leaf("cover", "Cover Letter")],
            "registration-form": [leaf("form", "Application Form")],
            "smpc": [leaf("smpc", "Summary of Product Characteristics")],
            "labelling": [leaf("labelling", "Labelling")],
            "patient-information-leaflet": [leaf("pl", "Package Leaflet")],
        },
    )
    root = etree.fromstring(xml)

    # build_regional_xml raises unless the whole document is DTD-valid, so
    # reaching here already proves the three pi-docs satisfy the spec.
    pi_docs = root.findall(".//pi-doc")
    assert [el.get("type") for el in pi_docs] == ["spc", "outer", "pl"]
    for el in pi_docs:
        assert el.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"
    assert [child.tag for child in root.find("m1-eu")] == [
        "m1-0-cover",
        "m1-2-form",
        "m1-3-pi",
    ]


# ---- the API refuses to take a derived value --------------------------------


async def test_the_api_refuses_a_derived_field_rather_than_dropping_it(auth_client):
    """A filer trying to type a shelf life onto the SmPC finds out NOW,
    not at export three weeks later.

    Pydantic's default is to ignore unknown keys, which is the worst of the
    three options: the write appears to succeed, the value vanishes, and
    the filer believes the SmPC says 36 months.
    """
    product = (
        await auth_client.post(
            "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
        )
    ).json()

    response = await auth_client.put(
        f"/products/{product['id']}/product-information",
        json={
            "therapeutic_indications": "Bacterial infections.",
            "shelf_life_months": 36,
        },
    )

    assert response.status_code == 422
    assert "shelf_life_months" in response.text


async def test_the_api_returns_the_derived_values_with_their_provenance(auth_client):
    """Read and write are asymmetric on purpose: the wizard has to SHOW
    section 6.3, while making unmistakable that it is not a field."""
    product = (
        await auth_client.post(
            "/products",
            json={
                "brand_name": "EXAMOX",
                "generic_name": "Amoxicillin",
                "shelf_life_months": 24,
                "storage_condition": "Store below 30 C.",
            },
        )
    ).json()
    await auth_client.put(
        f"/products/{product['id']}/product-information",
        json={"therapeutic_indications": "Bacterial infections."},
    )

    body = (await auth_client.get(f"/products/{product['id']}/product-information")).json()
    derived = {value["field"]: value for value in body["derived"]}

    assert derived["shelf_life"]["value"] == "24 months"
    assert "stability data" in derived["shelf_life"]["source"]
    assert derived["storage_condition"]["smpc_section"] == "6.4"
    assert "shelf_life_months" not in body


async def test_the_write_replaces_rather_than_merges(auth_client):
    """The sections on the filer's screen ARE the SmPC, so a
    contraindication they deleted has to be gone from the leaflet too."""
    product = (
        await auth_client.post(
            "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
        )
    ).json()
    url = f"/products/{product['id']}/product-information"

    await auth_client.put(url, json={"contraindications": ["Penicillin allergy", "Jaundice"]})
    body = (await auth_client.put(url, json={"contraindications": ["Penicillin allergy"]})).json()

    assert body["contraindications"] == ["Penicillin allergy"]


async def test_a_blank_contraindication_never_reaches_a_leaflet(auth_client):
    """An empty bullet printed into a patient document. The template has no
    way to tell a blank string from a deliberate one, so it is dropped
    here."""
    product = (
        await auth_client.post(
            "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
        )
    ).json()

    body = (
        await auth_client.put(
            f"/products/{product['id']}/product-information",
            json={"contraindications": ["Penicillin allergy", "   ", ""]},
        )
    ).json()

    assert body["contraindications"] == ["Penicillin allergy"]


async def test_the_frequency_of_a_side_effect_is_a_controlled_vocabulary(auth_client):
    """ "fairly often" is not a CIOMS band, and a document cannot order
    it."""
    product = (
        await auth_client.post(
            "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
        )
    ).json()

    response = await auth_client.put(
        f"/products/{product['id']}/product-information",
        json={"undesirable_effects": [{"effect": "Rash", "frequency": "fairly often"}]},
    )

    assert response.status_code == 422


async def test_someone_elses_product_information_looks_like_it_does_not_exist(
    auth_client, intruder_client
):
    product = (
        await auth_client.post(
            "/products", json={"brand_name": "EXAMOX", "generic_name": "Amoxicillin"}
        )
    ).json()
    await auth_client.put(
        f"/products/{product['id']}/product-information",
        json={"therapeutic_indications": "Bacterial infections."},
    )

    response = await intruder_client.get(f"/products/{product['id']}/product-information")

    assert response.status_code == 404


# ---- the three-way comparison, which is the screen --------------------------


async def test_the_comparison_reports_what_each_document_will_print(auth_client):
    """It asks the three CONTEXT BUILDERS, not the shared function once --
    a screen that only ever looked once would always agree, which would be
    a demonstration of nothing.
    """
    product_payload = {
        "brand_name": "EXAMOX",
        "generic_name": "Amoxicillin",
        "shelf_life_months": 24,
        "storage_condition": "Store below 30 C.",
        "pack_size": "10 x 10 blister",
    }
    product = (await auth_client.post("/products", json=product_payload)).json()
    project = (
        await auth_client.post(
            "/projects",
            json={"name": "EXAMOX renewal", "region": "NAFDAC", "product_id": product["id"]},
        )
    ).json()

    body = (
        await auth_client.get(f"/projects/{project['id']}/product-information/comparison")
    ).json()

    assert body["divergences"] == 0
    shelf_life = next(row for row in body["rows"] if row["field"] == "shelf_life")
    assert [value["section"] for value in shelf_life["values"]] == list(DOCUMENTS)
    assert {value["value"] for value in shelf_life["values"]} == {"24 months"}
    assert shelf_life["agrees"] is True
    assert shelf_life["smpc_section"] == "6.3"


# ---- the model's own shape --------------------------------------------------


def test_the_model_has_no_column_for_a_value_it_should_derive():
    """The absence IS the design, so it is asserted rather than left to a
    comment. A `shelf_life_months` column here would restore the defect in
    one migration."""
    columns = set(ProductInformation.__table__.columns.keys())

    for forbidden in (
        "shelf_life_months",
        "storage_condition",
        "pack_size",
        "strength",
        "excipients",
        "dosage_form",
    ):
        assert forbidden not in columns, (
            f"{forbidden} is a second copy of a value that already exists elsewhere; "
            f"the three product-information documents derive it instead"
        )


def test_a_product_can_hold_only_one_set_of_product_information():
    """ "The three documents read one row" is a database fact, not a
    convention the application maintains."""
    constraint = ProductInformation.__table__.columns["product_id"]
    assert constraint.unique is True


def test_the_lists_survive_a_row_that_holds_null_instead_of_an_empty_list():
    """A JSON column hands back whatever was stored. Every consumer would
    otherwise need the same guard, and the first to forget it raises
    TypeError inside a rendered document."""
    information = ProductInformation(contraindications=None, undesirable_effects=None)

    assert information.contraindication_terms == []
    assert information.adverse_effects == []


def test_the_batch_formula_now_carries_the_excipients_it_always_should_have():
    """A batch formula that lists only the actives is not a batch formula.
    Nothing said so until R28 existed."""
    project = _load(build_examox, buggy=False)
    components = {line.component for line in project.product.batch_formula if not line.is_active}

    assert {excipient.name for excipient in project.product.excipients} <= components


def test_a_line_added_to_the_formula_without_an_excipient_row_is_caught():
    """The same defect the seed plants, created here from scratch so the
    test does not depend on the fixture's choice of glidant."""
    project = _load(build_examox, buggy=False)
    project.product.batch_formula.append(
        BatchFormulaLine(component="Talc", spec="BP", qty_per_unit_mg=2.0, batch_size_units=250_000)
    )

    assert any("Talc" in f.message for f in _findings(project, "R28"))


async def test_reading_product_information_works_when_stability_results_exist(
    auth_client, session_factory
):
    """Regression: the derived block walked a relationship nobody loaded.

    `_read` attaches the derived values, which reach
    StabilityStudy.supported_months, which iterates that study's RESULTS.
    The route eager-loaded `Product.stability` and stopped one level short,
    so the last hop stayed lazy and raised MissingGreenlet on the async
    engine -- a 500 on both GET and PUT.

    WHY no test caught it: it only fires once a product actually has
    stability RESULTS, and every existing test here builds a product
    without them. The failure mode is the nastiest kind -- the endpoint
    works perfectly until the filing has real data in it.
    """
    # The EXAMOX seed carries four stability studies with 25 results between
    # them -- exactly the shape that triggers the bug, and already built.
    # owner_id goes in at BUILD time (not attach_owner afterwards) because
    # the seed otherwise creates its own User and the relationship would
    # win over a later FK assignment, leaving the product invisible here.
    project = build_examox(buggy=False, owner_id=auth_client.user_id)
    async with session_factory() as session:
        session.add(project)
        await session.commit()
        product_id = project.product_id

    written = await auth_client.put(
        f"/products/{product_id}/product-information",
        json={"therapeutic_indications": "Bacterial infections."},
    )
    assert written.status_code == 200, written.text

    read = await auth_client.get(f"/products/{product_id}/product-information")
    assert read.status_code == 200, read.text
    assert read.json()["derived"], "the derived block is the thing that walks stability"
