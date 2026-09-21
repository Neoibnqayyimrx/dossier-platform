"""The end-to-end proof (P24e task 11).

Every other test in this suite asserts that one part of the platform works.
This one asserts the claim the whole project makes: that a complete product,
entered as structured data, produces the dossier `docs/target-toc.yaml`
describes -- the contract that was derived, leaf by leaf, from a real filed
amlodipine 5 mg dossier.

It is slow, because it really does render, convert, place and zip the whole
package. That is the point: a fast version of this test would be a version
that did not build anything.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.storage import InMemoryStorageClient
from app.ctd.naming import leaf_filename
from app.ctd.build import build_ctd_package
from app.ctd.region_profiles import resolve_applicability
from app.ctd.toc import MODULE_TOC_LEAVES
from app.models import Base
from app.seed.amlodipine import build_amlodipine
from app.seed.documents import attach_certificate_documents, attach_every_uploaded_leaf
from app.target_toc import load_target_leaves
from app.validation.engine import run_all
import app.validation.rules  # noqa: F401  registers every rule on import


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


def _leaf_number_for(path: str) -> str | None:
    """The target leaf a placed file belongs to, or None.

    Since gap Phase 5a a file is named after its section number in ICH
    characters -- "3-2-p-4-1.pdf", "5-4-reference-list.pdf" -- with the
    subject in its folder, not its name. So the stem is looked up against
    the ICH spelling of every leaf number, trimming a trailing suffix until
    one matches. The EXACT stem is tried first, which is what stops
    "3-2-p-4-1" being trimmed to "3-2-p-4" and filed under 3.2.P.4.
    """
    if path == "toc.pdf":
        return None
    stem = path.rsplit("/", 1)[-1].removesuffix(".pdf")
    numbers = [leaf.number for leaf in load_target_leaves()] + list(MODULE_TOC_LEAVES)
    by_stem = {leaf_filename(number).removesuffix(".pdf"): number for number in numbers}
    candidate = stem
    while candidate not in by_stem:
        if "-" not in candidate:
            return None
        candidate = candidate.rsplit("-", 1)[0]
    return by_stem[candidate]


def test_the_worked_example_validates_clean():
    """No planted defects, and nothing the rule engine objects to.

    LAMOX and EXAMOX carry deliberate copy-paste bugs so the rules have
    something to catch. This fixture carries none, so an ERROR here is a
    real regression in either the seed or a rule -- which is exactly what
    makes it worth having.
    """
    project = build_amlodipine()
    storage = InMemoryStorageClient()
    attach_certificate_documents(project, storage)
    attach_every_uploaded_leaf(project, storage)

    report = run_all(project)
    assert report.errors() == [], [f.message for f in report.errors()]


async def test_a_complete_product_produces_the_dossier_the_contract_describes(db_factory):
    """The claim, end to end.

    Every applicable leaf in the target has a file in the built package,
    and every file in the package belongs to a leaf in the target. The
    second half matters as much as the first: a package containing
    documents the contract does not describe is a package nobody agreed to.
    """
    async with db_factory() as db:
        project = build_amlodipine()
        db.add(project)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        attach_every_uploaded_leaf(project, storage)
        result = await build_ctd_package(db, project, storage=storage)
        resolved = resolve_applicability(project)

    placed = [entry.path for entry in result.manifest if entry.path.endswith(".pdf")]
    target = {leaf.number: leaf for leaf in load_target_leaves()}
    scoped_out = {number for number, d in resolved.items() if not d.is_applicable}

    covered = {_leaf_number_for(path) for path in placed}
    covered.discard(None)

    # Every leaf the filing owes has a document.
    owed = set(target) - scoped_out
    assert not (owed - covered), sorted(owed - covered)

    # And nothing was placed that the contract does not describe. `toc.pdf`
    # is the only exception: it is packaging for the reader, not a leaf.
    unmapped = {path for path in placed if _leaf_number_for(path) is None}
    assert unmapped == {"toc.pdf"}, sorted(unmapped)


async def test_the_leaf_count_exceeds_98_only_where_a_leaf_legitimately_repeats(db_factory):
    """98 target leaves; 102 placed files. The difference is the lesson.

    A leaf number is not a document count. Four of the target's entries
    become more than one file in a real package, and each for a reason the
    contract itself declares:

      * 3.2.P.4.1 repeats per excipient -- this formulation has four.
      * 3.2.P.3.1 repeats per manufacturing site -- two, because the axis
        excludes the API maker (3.2.P.3.1 is about the FINISHED product,
        and naming the API site there files the wrong company as the maker
        of the medicine).
      * 3.2.P.7 repeats per pack -- a blister and a carton.
      * 3.3, 5.4 and 5.3.1.2 each carry a generated document BESIDE an
        uploaded one (`leaf_suffix`): two reference lists beside their
        literature packs, and a structured study summary beside the CRO's
        report.

    So "98/98 coverage" is a statement about the CONTRACT being satisfied,
    never a prediction of how many PDFs come out. A test asserting
    len(placed) == 98 would be asserting that no section ever repeats,
    which would fail on the first combination product.
    """
    async with db_factory() as db:
        project = build_amlodipine()
        db.add(project)
        await db.commit()
        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        attach_every_uploaded_leaf(project, storage)
        result = await build_ctd_package(db, project, storage=storage)

    placed = [entry.path for entry in result.manifest if entry.path.endswith(".pdf")]

    from collections import Counter

    per_leaf = Counter(number for path in placed if (number := _leaf_number_for(path)) is not None)
    repeated = {number: n for number, n in per_leaf.items() if n > 1}

    assert repeated == {
        "3.2.P.4.1": 4,
        "3.2.P.3.1": 2,
        "3.2.P.7": 2,
        "3.3": 2,
        "5.4": 2,
        "5.3.1.2": 2,
    }, repeated


async def test_the_package_is_a_valid_zip_and_rebuilds_identically(db_factory):
    """AGENTS.md 5's idempotence rule, on the largest package the platform
    produces. Checksums depend on it."""
    async with db_factory() as db:
        project = build_amlodipine()
        db.add(project)
        await db.commit()
        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        attach_every_uploaded_leaf(project, storage)

        first = await build_ctd_package(db, project, storage=storage)
        second = await build_ctd_package(db, project, storage=storage)

        assert storage.get(first.storage_key) == storage.get(second.storage_key)
        with zipfile.ZipFile(io.BytesIO(storage.get(first.storage_key))) as zf:
            assert zf.testzip() is None


async def test_the_worked_example_produces_a_dtd_valid_ectd_backbone(db_factory):
    """P24e task 11's other half: the same dossier, as an eCTD sequence,
    validated against `reference/ectd_dtd/ich-ectd-3-2.dtd`.

    WHY the region is switched to EU for this and not for the CTD build
    above: the eCTD backbone needs a REGIONAL backbone as well as
    `index.xml`, and EU is the only regional Module 1 this platform
    models (see EU_PROFILE's own note). The ICH half -- Modules 2 to 5,
    which is where all eleven of P24d's new sections live -- is common to
    every region, so this is the real test of them.

    The mechanical checks are run as well as the DTD, because DTD validity
    is a low bar: it says the tree is shaped legally, not that every leaf
    resolves, that the checksums match, or that no document is orphaned.
    """
    from app.ectd.build import build_ectd_sequence
    from app.ectd.validate import run_mechanical_checks
    from app.templating.instances import expand_sections
    from app.models import Region, Sequence
    from app.validation.engine import Severity

    async with db_factory() as db:
        project = build_amlodipine()
        project.region = Region.EU
        db.add(project)
        await db.commit()

        sequence = Sequence(project_id=project.id, number="0000")
        db.add(sequence)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        attach_every_uploaded_leaf(project, storage)
        result = await build_ectd_sequence(db, project, sequence, storage=storage)
        expected = {instance.key for instance in expand_sections(project)}

    with zipfile.ZipFile(io.BytesIO(storage.get(result.storage_key))) as zf:
        assert zf.testzip() is None
        files = {name: zf.read(name) for name in zf.namelist()}

    assert "0000/index.xml" in files
    assert "0000/index-md5.txt" in files

    # `prior_files` is empty because 0000 is the first sequence -- there is
    # nothing for a lifecycle operation to reference. `live_section_keys` is
    # what the sequence actually placed, which is what the required-sections
    # check compares against.
    findings = run_mechanical_checks(
        "0000",
        files,
        prior_files={},
        live_section_keys=set(result.operations),
        # What this PROJECT owes, not the whole registry -- the same source
        # `app/ectd/report.py` passes. It matters here: the registry holds
        # NAFDAC-only Module 1 leaves (1.2.1, 1.2.14, 1.4.2, 1.6) that an EU
        # sequence correctly never emits, and check M12 would otherwise
        # report every one of them as missing from a package that is right.
        expected_section_keys=expected,
    )
    blocking = [f for f in findings if f.severity is Severity.ERROR]
    assert blocking == [], [f.message for f in blocking]

    # The P24d sections really are in the backbone, not merely on disk. A
    # leaf written into the package and omitted from index.xml is present
    # to a file browser and invisible to the agency's software -- which is
    # the exact failure mode P18's heading-path entries exist to prevent.
    index = files["0000/index.xml"].decode()
    for element in (
        "m3-2-p-2-pharmaceutical-development",
        "m3-2-p-3-3-description-of-manufacturing-process-and-process-controls",
        "m3-2-s-2-2-description-of-manufacturing-process-and-process-controls",
        "m2-2-introduction",
        "m3-3-literature-references",
    ):
        assert element in index, element


async def test_the_worked_example_as_an_fda_anda(db_factory):
    """gap Phase 4c: the same complete dossier, published to FDA.

    The EU test above proves Modules 2-5 against the ICH DTD. This one
    proves the FDA half: us-regional.xml against FDA's DTD (M02), every
    code in it against FDA's published lists (M13), and the whole package
    through M01-M13 with no ERROR. The dossier is re-targeted by
    `app.seed.fda.as_fda_original_application` -- an ANDA, because the
    worked example is a multisource generic -- with identifiers chosen so a
    seed can never be mistaken for a real application.
    """
    from app.ectd.build import build_ectd_sequence
    from app.ectd.validate import run_mechanical_checks
    from app.models import Sequence
    from app.seed.fda import as_fda_original_application
    from app.templating.instances import expand_sections
    from app.validation.engine import Severity
    from lxml import etree

    async with db_factory() as db:
        project = as_fda_original_application(build_amlodipine())
        assert run_all(project).errors() == []
        db.add(project)
        await db.commit()

        # FDA numbering starts at 0001 (RegionProfile.first_sequence_number).
        sequence = Sequence(project_id=project.id, number="0001")
        db.add(sequence)
        await db.commit()

        storage = InMemoryStorageClient()
        attach_certificate_documents(project, storage)
        attach_every_uploaded_leaf(project, storage)
        result = await build_ectd_sequence(db, project, sequence, storage=storage)
        expected = {instance.key for instance in expand_sections(project)}

    with zipfile.ZipFile(io.BytesIO(storage.get(result.storage_key))) as zf:
        assert zf.testzip() is None
        files = {name: zf.read(name) for name in zf.namelist()}

    findings = run_mechanical_checks(
        "0001",
        files,
        prior_files={},
        live_section_keys=set(result.operations),
        expected_section_keys=expected,
    )
    blocking = [f for f in findings if f.severity is Severity.ERROR]
    assert blocking == [], [f"{f.rule_id}: {f.message}" for f in blocking]

    # No EU remnants, and FDA's Module 1 is where FDA looks for it.
    assert not any("/m1/eu/" in name for name in files)
    regional = etree.fromstring(files["0001/m1/us/us-regional.xml"])
    number = regional.find(
        "admin/application-set/application/application-information/application-number"
    )
    assert number.get("application-type") == "fdaat2"  # ANDA
    headings = {leaf.getparent().tag for leaf in regional.iter("leaf")}
    assert {
        "m1-2-cover-letters",
        "m1-14-1-1-draft-carton-and-container-labels",
        "m1-14-1-3-draft-labeling-text",
    } <= headings

    # Modules 2-5 are the same ICH backbone whichever region files them.
    index = files["0001/index.xml"].decode()
    for element in ("m3-2-p-2-pharmaceutical-development", "m2-2-introduction"):
        assert element in index, element
