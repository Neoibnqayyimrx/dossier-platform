"""BackboneBuilder interface (P09).

WHY this interface exists at all, with exactly one implementation today:
the reference doc is explicit that P12 (eCTD v4.0 / HL7 RPS) must slot in
as a `V4RpsBackboneBuilder` later "without touching assembly, templating,
validation, or build orchestration". `app.ectd.build`'s orchestrator talks
only to this interface, never to `index_xml`/`regional` directly, so
adding v4.0 later is "write a new BackboneBuilder", not "rewrite build.py"
-- the same open/closed payoff `app.ctd.region_profiles`' `RegionProfile`
already proved for Module 1 variation in P08.
"""

from __future__ import annotations

import posixpath
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.ectd.index_xml import build_index_xml
from app.templating.instances import repeat_element_info
from app.ectd.leaf import Leaf, leaf_id_for
from app.ectd.checksum import index_md5_line, md5_hex
from app.ectd.regional import REGIONAL_XML_RELATIVE_PATH, build_regional_xml
from app.models.enums import Region
from app.models.project import Project


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
        sequence_number: str,
        related_sequence_numbers: list[str],
        ich_leaves: dict[str, Leaf],
        regional_leaves_by_slot: dict[str, list[Leaf]],
        submission_unit_type: str = "initial",
    ) -> BackboneResult: ...


class V322BackboneBuilder(BackboneBuilder):
    """eCTD v3.2.2: ICH backbone (`app.ectd.index_xml`) + regional
    backbone. EU only today -- FDA's regional DTD/envelope aren't built
    yet (see the P09 build-log entry for the scope call); requesting FDA
    raises rather than silently producing something DTD-invalid or, worse,
    DTD-valid-but-wrong."""

    def build(
        self,
        project: Project,
        sequence_number: str,
        related_sequence_numbers: list[str],
        ich_leaves: dict[str, Leaf],
        regional_leaves_by_slot: dict[str, list[Leaf]],
        # P27: what KIND of transaction this sequence is. Defaulted so the
        # older callers and tests that predate the field keep working and
        # keep getting exactly what they got before.
        submission_unit_type: str = "initial",
    ) -> BackboneResult:
        if project.region != Region.EU:
            raise NotImplementedError(
                f"V322BackboneBuilder only supports the EU regional backbone today "
                f"(got region={project.region!r}); FDA is not built yet"
            )

        # WHY regional first (gap Phase 4a): index.xml carries a leaf for
        # the regional file, and a leaf carries its file's checksum -- so
        # the regional bytes have to exist before index.xml can be written.
        regional_xml_bytes = build_regional_xml(
            project,
            sequence_number,
            related_sequence_numbers,
            regional_leaves_by_slot,
            submission_unit_type,
        )
        index_xml_bytes = build_index_xml(
            ich_leaves,
            repeat_info=repeat_element_info(project),
            regional_leaf=regional_backbone_leaf(
                REGIONAL_XML_RELATIVE_PATH, regional_xml_bytes, sequence_number
            ),
        )
        index_md5_bytes = index_md5_line(index_xml_bytes).encode("utf-8")

        return BackboneResult(
            index_xml=index_xml_bytes,
            index_md5=index_md5_bytes,
            regional_xml=regional_xml_bytes,
            regional_xml_relative_path=REGIONAL_XML_RELATIVE_PATH,
        )
