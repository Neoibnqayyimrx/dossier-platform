"""BackboneBuilder interface (P09), and the regional seam (gap Phase 4b).

WHY this interface exists at all, with exactly one implementation today:
the reference doc is explicit that P12 (eCTD v4.0 / HL7 RPS) must slot in
as a `V4RpsBackboneBuilder` later "without touching assembly, templating,
validation, or build orchestration". `app.ectd.build`'s orchestrator talks
only to this interface, never to `index_xml`/`regional` directly, so
adding v4.0 later is "write a new BackboneBuilder", not "rewrite build.py"
-- the same open/closed payoff `app.ctd.region_profiles`' `RegionProfile`
already proved for Module 1 variation in P08.

WHY region is a table INSIDE the v3.2.2 builder, not a builder per region
(gap Phase 4b): the two vary independently. Every v3.2.2 sequence has the
same ICH index.xml; only the regional half differs. A class per region
would fuse the two axes, and P12 would then need a v4.0 class per region
as well. So `BackboneBuilder` is the SPEC-VERSION seam and
`REGIONAL_BACKBONES` is the REGION seam, and adding FDA was one row.
"""

from __future__ import annotations

import posixpath
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.ectd.checksum import index_md5_line, md5_hex
from app.ectd.errors import EctdNotSupportedError
from app.ectd.index_xml import build_index_xml
from app.ectd.leaf import Leaf, leaf_id_for
from app.ectd import regional as eu_regional
from app.ectd import us_regional
from app.models.enums import Region
from app.models.project import Project
from app.templating.instances import repeat_element_info


@dataclass(frozen=True)
class SequenceContext:
    """What a regional envelope may need to know about THIS transaction.

    Different regions read different fields: the EU envelope states the
    related sequence, FDA's states the first sequence of the regulatory
    activity (its `submission-id`). A context object rather than a longer
    parameter list, so the next region's field is an addition here rather
    than a signature change through three modules.
    """

    number: str
    related_sequence_numbers: tuple[str, ...] = ()
    # The EU vocabulary (app.models.enums.SubmissionUnitType) -- each
    # region's builder maps it to its own.
    submission_unit_type: str = "initial"
    # The first sequence of the regulatory activity this one belongs to.
    # Defaults to this sequence, which is right for a project's first.
    first_sequence_number: str | None = None


@dataclass(frozen=True)
class RegionalBackbone:
    """One region's half of an eCTD v3.2.2 sequence."""

    # Where the regional file sits in a sequence, e.g. "m1/us/us-regional.xml".
    relative_path: str
    # The DTD it must satisfy -- read by the builder before returning and,
    # since gap Phase 4c, by the mechanical check M02 on the built package.
    dtd_path: Path
    # util/... path in the package -> file name in reference/ectd_dtd/.
    util_files: dict[str, str]
    build: Callable[[Project, SequenceContext, dict[str, list[Leaf]]], bytes] = field(repr=False)
    # Refuses (EctdNotSupportedError) what can be refused before anything is
    # rendered. Optional: the EU envelope has nothing to check up front.
    preflight: Callable[[Project, SequenceContext], object] | None = field(default=None, repr=False)


REGIONAL_BACKBONES: dict[Region, RegionalBackbone] = {
    Region.EU: RegionalBackbone(
        relative_path=eu_regional.REGIONAL_XML_RELATIVE_PATH,
        dtd_path=eu_regional.DTD_PATH,
        util_files={
            "util/dtd/eu-regional.dtd": "eu-regional.dtd",
            "util/dtd/eu-envelope.mod": "eu-envelope.mod",
            "util/dtd/eu-leaf.mod": "eu-leaf.mod",
            "util/style/eu-regional.xsl": "eu-regional.xsl",
        },
        build=lambda project, context, leaves: eu_regional.build_regional_xml(
            project,
            context.number,
            list(context.related_sequence_numbers),
            leaves,
            context.submission_unit_type,
        ),
    ),
    Region.FDA: RegionalBackbone(
        relative_path=us_regional.REGIONAL_XML_RELATIVE_PATH,
        dtd_path=us_regional.DTD_PATH,
        # ICH v3.2.2 Table 6-2 lists us-regional-vx-x.dtd in every
        # sequence's util/dtd, even though FDA's own header points the
        # DOCTYPE at accessdata.fda.gov -- see app.ectd.us_regional.
        util_files={
            "util/dtd/us-regional-v3-3.dtd": "us-regional-v3-3.dtd",
            "util/style/us-regional.xsl": "us-regional.xsl",
        },
        build=lambda project, context, leaves: us_regional.build_us_regional_xml(
            project,
            context.number,
            context.first_sequence_number or context.number,
            leaves,
            context.submission_unit_type,
        ),
        preflight=lambda project, context: us_regional.preflight(
            project,
            context.number,
            context.first_sequence_number or context.number,
            context.submission_unit_type,
        ),
    ),
}

# WHY a reason per region rather than one generic message: "not built yet"
# is the wrong thing to tell a NAFDAC filer. NAFDAC was checked against its
# in-force guideline and takes CTD, not eCTD -- nothing is missing, and the
# message has to point at the package that IS right for them.
_NO_BACKBONE_REASON: dict[Region, str] = {
    Region.NAFDAC: (
        "NAFDAC takes CTD, not eCTD: its registration guideline (DR&R-GDL-005-03) "
        "asks for CTD documents uploaded to NAPAMS and never an XML backbone. Build "
        "the CTD package instead (POST /projects/{id}/build/ctd). See "
        "docs/decisions/0001-nafdac-format.md."
    ),
}


def regional_backbone_for(region: Region) -> RegionalBackbone:
    try:
        return REGIONAL_BACKBONES[region]
    except KeyError:
        reason = _NO_BACKBONE_REASON.get(
            region, f"No eCTD regional backbone is built for region {region.value}."
        )
        raise EctdNotSupportedError(reason) from None


@dataclass
class BackboneResult:
    index_xml: bytes
    index_md5: bytes
    regional_xml: bytes
    regional_xml_relative_path: str  # e.g. "m1/eu/eu-regional.xml"


def regional_backbone_leaf(relative_path: str, xml_bytes: bytes, sequence_number: str) -> Leaf:
    """The index.xml leaf that points at this sequence's regional backbone.

    Always `new`, never replace -- the ICH spec is explicit that each
    sequence's regional file is its own document, not a revision of the
    last one. Its ID is keyed like any other leaf's, on a name no CTD
    section can take (section keys are numbers or "certificate:<uuid>").
    """
    return Leaf(
        id=leaf_id_for("regional-backbone", sequence_number),
        title=posixpath.basename(relative_path),
        href=relative_path,
        checksum=md5_hex(xml_bytes),
        operation="new",
    )


class BackboneBuilder(ABC):
    """One implementation per eCTD spec version."""

    @abstractmethod
    def build(
        self,
        project: Project,
        context: SequenceContext,
        ich_leaves: dict[str, Leaf],
        regional_leaves_by_slot: dict[str, list[Leaf]],
    ) -> BackboneResult: ...


class V322BackboneBuilder(BackboneBuilder):
    """eCTD v3.2.2: the ICH backbone (`app.ectd.index_xml`) plus the
    project's region's regional backbone, from `REGIONAL_BACKBONES`.

    A region with no entry raises `EctdNotSupportedError` rather than
    producing something DTD-invalid or, worse, DTD-valid-but-wrong."""

    def build(
        self,
        project: Project,
        context: SequenceContext,
        ich_leaves: dict[str, Leaf],
        regional_leaves_by_slot: dict[str, list[Leaf]],
    ) -> BackboneResult:
        regional = regional_backbone_for(project.region)

        # WHY regional first (gap Phase 4a): index.xml carries a leaf for
        # the regional file, and a leaf carries its file's checksum -- so
        # the regional bytes have to exist before index.xml can be written.
        regional_xml_bytes = regional.build(project, context, regional_leaves_by_slot)
        index_xml_bytes = build_index_xml(
            ich_leaves,
            repeat_info=repeat_element_info(project),
            regional_leaf=regional_backbone_leaf(
                regional.relative_path, regional_xml_bytes, context.number
            ),
        )
        index_md5_bytes = index_md5_line(index_xml_bytes).encode("utf-8")

        return BackboneResult(
            index_xml=index_xml_bytes,
            index_md5=index_md5_bytes,
            regional_xml=regional_xml_bytes,
            regional_xml_relative_path=regional.relative_path,
        )
