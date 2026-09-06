"""Tests: section repetition beyond the drug substance (P19).

P13 proved a section could repeat; it proved it for exactly one axis, and
in doing so encoded three assumptions that only became visible under a
second axis -- that a subject has an `inn_name`, that a subject's folder is
under `32s/`, and that "has a subject" and "repeats per drug substance"
are the same predicate. These tests pin the generalisation, and then pin
the four things the new sections have to get right: identity, placement,
determinism, and agreement with the data they share with other sections.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ctd.structure import REPEAT_FOLDERS, folder_for_section_instance
from app.models import (
    Base,
    Certificate,
    CertificateType,
    ExcipientOrigin,
    Packaging,
    PackagingComponent,
    PackagingRole,
)
import app.validation.rules  # noqa: F401  registers rules
from app.seed.ampiclox import build_ampiclox
from app.seed.examox import build_examox
from app.target_toc import load_target_leaves
from app.templating.context import build_context
from app.templating.instances import REPEAT_AXES, expand_sections, get_repeat_axis
from app.templating.registry import SECTIONS
from app.validation.engine import run_all


def _load(builder, **kwargs):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    project = builder(buggy=False, **kwargs)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


# ---- the axis table is the contract ----------------------------------------


def test_every_repeat_axis_in_the_target_is_resolvable():
    """The target TOC names four axes; a registry that knows three would
    fail on the fourth section someone registers, at build time, in front
    of whoever was assembling a filing that day."""
    declared = {leaf.repeat for leaf in load_target_leaves() if leaf.repeat}
    assert declared <= set(REPEAT_AXES), declared - set(REPEAT_AXES)


def test_registry_repeat_axes_match_the_target():
    """A registered section repeats along the axis the CONTRACT says it
    does. Two answers to "what is 3.2.P.7 repeated per" is how a package
    and its table of contents come to describe different dossiers."""
    target = {leaf.number: leaf.repeat for leaf in load_target_leaves()}
    for number, spec in SECTIONS.items():
        if number in target and not spec.is_statement:
            assert spec.repeat == target[number], number


def test_an_unknown_axis_raises_rather_than_producing_nothing():
    with pytest.raises(KeyError):
        get_repeat_axis("per_full_moon")


def test_every_repeating_section_has_a_folder_on_its_own_axis():
    """`folder_for_section_instance` raises on a miss (that is the point),
    so a registered repeating section with no mapping is a build that dies
    the first time someone assembles a package. Caught here instead."""
    for number, spec in SECTIONS.items():
        if spec.repeat is None:
            continue
        assert number in REPEAT_FOLDERS[spec.repeat].tails, number


# ---- identity: what a project actually owes ---------------------------------


def test_a_combination_product_owes_two_copies_of_every_per_substance_section():
    instances = expand_sections(_load(build_ampiclox))
    per_substance = [i for i in instances if i.spec.repeat == "drug_substance"]
    by_number: dict[str, list[str]] = {}
    for instance in per_substance:
        by_number.setdefault(instance.number, []).append(instance.key)

    # Five sections repeat per substance after P19 (3.2.S.1, 3.2.S.4.1 from
    # P13; 3.2.S.2.1, 3.2.S.5, 3.2.S.6 new here).
    assert set(by_number) == {"3.2.S.1", "3.2.S.4.1", "3.2.S.2.1", "3.2.S.5", "3.2.S.6"}
    for number, keys in by_number.items():
        assert keys == [f"{number}-ampicillin", f"{number}-cloxacillin"], number


def test_a_three_pack_product_owes_three_container_closure_documents():
    project = _load(build_examox)
    project.product.packaging = [
        Packaging(
            role=PackagingRole.DRUG_PRODUCT,
            component=PackagingComponent.PRIMARY,
            description="Alu/PVC blister, 10 capsules",
            material="Alu-PVC",
        ),
        Packaging(
            role=PackagingRole.DRUG_PRODUCT,
            component=PackagingComponent.PRIMARY,
            description="HDPE bottle, 100 capsules",
            material="HDPE",
        ),
        Packaging(
            role=PackagingRole.DRUG_PRODUCT,
            component=PackagingComponent.SECONDARY,
            description="Printed carton with leaflet",
        ),
    ]
    packs = [i for i in expand_sections(project) if i.number == "3.2.P.7"]
    folders = {folder_for_section_instance(i.number, i.subject_slug) for i in packs}

    # Three packs, three documents, three folders. A pack sharing a folder
    # with another pack is a file that overwrites another file.
    assert len(packs) == 3
    assert len(folders) == 3
    assert all(
        f.startswith("m3/32-body-data/32p/32p7-container-closure-system/pack-") for f in folders
    )


def test_two_packs_that_slugify_alike_are_refused_rather_than_merged():
    """The assumption the drug-substance axis hid: two actives cannot share
    an INN, but two packs can easily share a component and have no material
    recorded -- and the second would overwrite the first."""
    project = _load(build_examox)
    project.product.packaging = [
        Packaging(
            role=PackagingRole.DRUG_PRODUCT,
            component=PackagingComponent.PRIMARY,
            description="Alu/PVC blister, 10 capsules",
        ),
        Packaging(
            role=PackagingRole.DRUG_PRODUCT,
            component=PackagingComponent.PRIMARY,
            description="Alu/alu blister, 10 capsules",
        ),
    ]
    with pytest.raises(ValueError, match="overwrite"):
        expand_sections(project)


def test_manufacturing_sites_repeat_but_the_api_site_is_not_one_of_them():
    """3.2.P.3.1 is about the DRUG PRODUCT. Naming the API's maker there
    files the wrong company as the maker of the medicine -- and the API
    site is not omitted, it is named in 3.2.S.2.1 instead."""
    project = _load(build_ampiclox)
    sites = [i for i in expand_sections(project) if i.number == "3.2.P.3.1"]
    assert [i.subject_name for i in sites] == ["Exagon"]
    assert "Exagon API Division" not in {i.subject_name for i in sites}

    api_sections = [i for i in expand_sections(project) if i.number == "3.2.S.2.1"]
    named = {
        row["value"]
        for i in api_sections
        for row in build_context("3.2.S.2.1", project, subject=i.subject)["manufacturer_details"]
        if row["label"] == "Name"
    }
    assert named == {"Exagon API Division"}


def test_folders_are_distinct_per_subject_on_every_axis():
    project = _load(build_ampiclox)
    repeated = [i for i in expand_sections(project) if i.subject is not None]
    folders = [folder_for_section_instance(i.number, i.subject_slug) for i in repeated]
    # One folder per (section, subject). Two instances sharing a folder is
    # two PDFs at one path, i.e. one of them silently missing.
    assert len(set(zip(folders, (i.key for i in repeated)))) == len(repeated)
    assert len(set(folders)) == len(folders)


# ---- determinism ------------------------------------------------------------


def test_two_expansions_of_one_project_produce_identical_keys_and_paths():
    """AGENTS.md §5's idempotent-builder rule, at the layer P19 changed.

    These strings end up in MD5-checksummed paths, so a subject order that
    depended on a set's iteration order, or a slug that included anything
    volatile, would produce a different package on every build -- and the
    eCTD lifecycle's whole diff model rests on the paths being stable.
    """
    project = _load(build_ampiclox)

    def snapshot():
        # Module 1's placement is regional and comes from the profile, not
        # from this map -- see folder_for_section's own error message.
        return [
            (
                i.key,
                i.title,
                folder_for_section_instance(i.number, i.subject_slug)
                if i.number not in ("1.0", "1.2")
                else None,
            )
            for i in expand_sections(project)
        ]

    assert snapshot() == snapshot()


# ---- agreement with the data other sections already use ---------------------


def test_batch_formula_cannot_disagree_with_the_composition_table():
    """3.2.P.3.2 and 3.2.P.1 are the same rows scaled differently.

    They agree because neither holds its own copy of the numbers -- both
    read product.batch_formula. This test would fail the moment someone
    "fixed" one of them by typing the values in.
    """
    project = _load(build_ampiclox)
    composition = build_context("3.2.P.1", project)["batch_formula"]
    formula = build_context("3.2.P.3.2", project)["batch_formula"]

    assert [line.component for line in composition] == [row["component"] for row in formula]
    assert [line.qty_per_unit_mg for line in composition] == [
        row["qty_per_unit_mg"] for row in formula
    ]
    # And the batch column is arithmetic on those same rows, not a second
    # declared number: 250 mg x 100,000 units = 25 kg.
    assert formula[0]["batch_qty_kg"] == pytest.approx(25.0)


def test_drug_substance_packaging_never_answers_for_the_drug_product():
    """The P19 task the prompt was most explicit about: one Packaging model
    must not silently serve both 3.2.S.6 and 3.2.P.7."""
    project = _load(build_ampiclox)
    substance_packs = build_context("3.2.S.6", project, subject=project.product.apis[0])[
        "packaging"
    ]
    product_packs = [i.subject for i in expand_sections(project) if i.number == "3.2.P.7"]

    assert substance_packs
    assert product_packs
    assert all(p.role is PackagingRole.DRUG_SUBSTANCE for p in substance_packs)
    assert all(p.role is PackagingRole.DRUG_PRODUCT for p in product_packs)
    assert not {id(p) for p in substance_packs} & {id(p) for p in product_packs}


# ---- 3.2.P.4.5 and rule R21 -------------------------------------------------


def test_tse_statement_names_the_animal_origin_excipient():
    context = build_context("3.2.P.4.5", _load(build_ampiclox))
    assert [row["name"] for row in context["excipients_of_concern"]] == ["Gelatin capsule shell"]
    assert "are of human or animal origin" in context["origin_statement"]


def test_tse_statement_is_the_blanket_one_when_nothing_is_of_animal_origin():
    project = _load(build_ampiclox)
    for excipient in project.product.excipients:
        excipient.origin = ExcipientOrigin.SYNTHETIC
    context = build_context("3.2.P.4.5", project)
    assert context["excipients_of_concern"] == []
    assert context["origin_statement"].startswith("No excipient")


def test_an_undeclared_origin_is_named_as_not_covered():
    """Silence is not a claim of synthetic origin. The leaf says so rather
    than quietly extending the statement over a material nobody classified."""
    project = _load(build_ampiclox)
    project.product.excipients[0].origin = None
    context = build_context("3.2.P.4.5", project)
    assert "Origin not yet declared for: Starch" in context["undeclared_statement"]


def test_r21_blocks_export_when_animal_origin_has_no_certificate():
    project = _load(build_ampiclox)
    project.product.certificates = [
        c for c in project.product.certificates if c.certificate_type is not CertificateType.TSE_BSE
    ]
    findings = [f for f in run_all(project).findings if f.rule_id == "R21"]
    assert len(findings) == 1
    assert "Gelatin capsule shell" in findings[0].message
    assert not run_all(project).is_exportable()


def test_r21_is_satisfied_by_a_tse_certificate():
    project = _load(build_ampiclox)
    assert [f for f in run_all(project).findings if f.rule_id == "R21"] == []


def test_r21_says_nothing_about_an_excipient_nobody_classified():
    """A null origin is a fact nobody has been asked for. Erroring there
    would block every project that predates the field on data it was never
    given -- the rendered leaf is where that gap belongs."""
    project = _load(build_examox)
    for excipient in project.product.excipients:
        excipient.origin = None
    project.product.certificates = [
        c for c in project.product.certificates if c.certificate_type is not CertificateType.TSE_BSE
    ]
    assert [f for f in run_all(project).findings if f.rule_id == "R21"] == []


def test_a_tse_certificate_row_alone_satisfies_r21():
    """The known limitation, pinned so it is a decision and not a surprise:
    Certificate has no excipient FK, so one certificate covers every
    animal-origin excipient on the product."""
    project = _load(build_examox)
    project.product.certificates = [
        c for c in project.product.certificates if c.certificate_type is not CertificateType.TSE_BSE
    ]
    project.product.excipients[0].origin = ExcipientOrigin.ANIMAL
    assert [f for f in run_all(project).findings if f.rule_id == "R21"]

    project.product.certificates.append(
        Certificate(certificate_type=CertificateType.TSE_BSE, issuing_authority="Supplier")
    )
    assert [f for f in run_all(project).findings if f.rule_id == "R21"] == []


# ---- 3.2.R ------------------------------------------------------------------


def test_regional_information_comes_from_the_region_profile():
    context = build_context("3.2.R", _load(build_examox))
    assert context["region"] == "NAFDAC"
    assert [item.title for item in context["regional_information"]] == [
        "Executed production documents",
        "Analytical procedures and validation information",
    ]
    assert "NAFDAC" in context["regional_statement"]


# ---- the whole way through: two builds, identical paths and checksums -------


@pytest.fixture
async def db_factory():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

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


async def test_two_builds_of_a_repeated_dossier_are_byte_identical(db_factory):
    """The DoD's second test, run through the real pipeline rather than
    over the instance layer alone (which `test_two_expansions...` covers).

    A combination product with two actives and two packs exercises three
    axes at once. What must hold is that the SECOND build produces the same
    leaf paths and the same MD5s -- because the eCTD lifecycle model
    identifies a document by its path and detects a change by its checksum,
    so a builder that shuffles either invents changes that never happened.
    """
    from app.assembly.assemble import assemble_project
    from app.core.storage import InMemoryStorageClient
    from app.seed.documents import attach_certificate_documents

    async with db_factory() as db:
        project = build_ampiclox(buggy=False)
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)

        def leaves(manifest):
            # Module 1 is placed by the REGION PROFILE, not by the shared
            # folder map -- its layout is the regional part of a CTD (see
            # region_profiles' opening docstring), and that includes the
            # attached CPP at 1.2.7. Asking the Modules 2-5 map about it
            # raises, which is the map behaving correctly.
            return [
                (
                    entry.section,
                    entry.filename,
                    entry.section_number
                    if entry.section_number.startswith("1.")
                    else folder_for_section_instance(entry.section_number, entry.subject_slug),
                    entry.md5,
                )
                for entry in manifest
            ]

        first = leaves(await assemble_project(db, project, storage=storage))
        second = leaves(await assemble_project(db, project, storage=storage))

        assert first == second
        # Sanity: this fixture really does exercise repetition, so the
        # assertion above is not trivially true of a flat dossier.
        assert sum(1 for key, *_ in first if key.startswith("3.2.S.1-")) == 2
        assert sum(1 for key, *_ in first if key.startswith("3.2.P.7-")) == 2


def test_subject_order_does_not_depend_on_the_order_rows_come_back_in():
    """Paths survive a reordered collection because they carry the subject's
    name; the package's FILE ORDER would not, and a zip whose entries move
    is not byte-identical. So the expansion sorts."""
    project = _load(build_ampiclox)
    forwards = [i.key for i in expand_sections(project)]
    project.product.apis.reverse()
    project.product.packaging.reverse()
    assert [i.key for i in expand_sections(project)] == forwards


def test_every_new_section_reaches_the_ectd_backbone():
    """`build_index_xml` SILENTLY SKIPS a leaf whose key has no heading path
    -- that is how Module 1 stays out of index.xml. A repeated key
    ("3.2.P.7-pack-hdpe") that failed the lookup would therefore be written
    to disk, checksummed, listed in the CTD table of contents, and invisible
    to the agency's software. This is the test that says otherwise.
    """
    from app.ectd.index_xml import build_index_xml
    from app.ectd.leaf import Leaf
    from app.templating.instances import drug_substance_info

    project = _load(build_ampiclox)
    leaves = {}
    for instance in expand_sections(project):
        if instance.number in ("1.0", "1.2"):
            continue  # Module 1 belongs to the regional backbone, by design
        folder = folder_for_section_instance(instance.number, instance.subject_slug)
        leaves[instance.key] = Leaf(
            id=f"ID-{instance.key.replace('.', '-')}-0000",
            title=instance.title,
            href=f"{folder}/{instance.key}.pdf",
            checksum="0" * 32,
            operation="new",
        )

    # Raises if the result is not DTD-valid, which is the other half of the
    # guarantee: the new headings are real element names in real positions.
    xml = build_index_xml(leaves, substance_info=drug_substance_info(project))
    assert xml.count(b"<leaf") == len(leaves)

    # Both packs under ONE m3-2-p-7 element: the DTD declares that heading
    # once with `leaf*` content, unlike m3-2-s-drug-substance which repeats.
    assert xml.count(b"<m3-2-p-7-container-closure-system>") == 1
    assert xml.count(b"<m3-2-s-drug-substance ") == 2


def test_a_pack_with_no_role_yet_is_still_the_drug_products():
    """`role` has a Python-side default, and SQLAlchemy applies those at
    FLUSH -- so an in-memory project has `role is None`. If that read as
    "not the drug product", 3.2.P.7 would silently vanish from a dossier
    built before a commit."""
    project = build_examox(buggy=False)  # deliberately NOT persisted
    for pack in project.product.packaging:
        pack.role = None
    packs = [i for i in expand_sections(project) if i.number == "3.2.P.7"]
    assert packs


def test_r12_does_not_read_the_api_drum_as_the_products_carton():
    """R12 predates the role, and once packaging could describe two
    materials it had to say which one it meant: an API drum's label is not
    where the finished product's pack size is printed."""
    from app.models import PackagingComponent as Component

    project = _load(build_examox)
    project.product.pack_size = "10 x 10 blister"
    project.product.packaging = [
        Packaging(
            role=PackagingRole.DRUG_SUBSTANCE,
            component=Component.CARTON,
            description="Fibre drum, 25 kg — 10 x 10 blister",
        )
    ]
    # The drum's description contains the product's pack size verbatim, and
    # must still not satisfy the check -- nor is there anything left for it
    # to check, so it stays silent rather than warning about a carton the
    # product does not have.
    assert [f for f in run_all(project).findings if f.rule_id == "R12"] == []
