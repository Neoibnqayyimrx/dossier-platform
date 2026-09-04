"""Region profile config for Module 1 (P08).

WHY this is config, not code branching in the builder: Module 1 is the one
part of a CTD that genuinely varies by region (nafdac-vs-fda-ema-scope.md).
`app.ctd.build`'s orchestrator never asks "is this NAFDAC?" -- it just
walks whatever `Module1Slot` list the project's region resolves to. Adding
FDA or EU support later is "write a new `RegionProfile`," not "add an if
branch to the builder."

Each slot is backed by exactly one of: a P07-rendered `SECTIONS` entry
(`section_number`), a set of `CertificateType`s (a slot can hold several
certificates of matching types), or a set of `DeclarationType`s -- never
more than one kind, since each source is fetched and rendered differently
in `build.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import CertificateType, DeclarationType, Region


@dataclass(frozen=True)
class Module1Slot:
    slot_id: str
    title: str
    folder: str
    section_number: str | None = None
    certificate_types: tuple[CertificateType, ...] = ()
    declaration_types: tuple[DeclarationType, ...] = ()


@dataclass(frozen=True)
class RegionProfile:
    region: Region
    module1_slots: list[Module1Slot]

    # WHY these are separate from the slots' `certificate_types` above:
    # a slot lists what it ACCEPTS (any certificate of these types is
    # filed here), while these list what the region REQUIRES before the
    # dossier may be exported. A NAFDAC filing accepts a CEP and a CoA
    # but demands a CPP; the two lists answer different questions.
    #
    # WHY here rather than as constants in app.validation.rules (P15a):
    # they were in both places -- the rules held the requirement and the
    # UI would have needed its own third copy to know which Module 1
    # fields to ask for. Config, one copy, served to the frontend by
    # app.api.routers.regions (AGENTS.md §5 "config over hard-coding").
    required_certificate_types: tuple[CertificateType, ...] = ()
    required_declaration_types: tuple[DeclarationType, ...] = ()


NAFDAC_PROFILE = RegionProfile(
    region=Region.NAFDAC,
    required_certificate_types=(CertificateType.CPP,),
    required_declaration_types=(
        DeclarationType.POWER_OF_ATTORNEY,
        DeclarationType.DECLARATION_OF_AUTHENTICITY,
    ),
    module1_slots=[
        Module1Slot(
            slot_id="cover-letter",
            title="Cover Letter",
            folder="m1/10-cover-letter",
            section_number="1.0",
        ),
        Module1Slot(
            slot_id="registration-form",
            title="Application / Registration Form",
            folder="m1/12-administrative-information",
            section_number="1.2",
        ),
        Module1Slot(
            slot_id="certificates",
            title="Certificates",
            folder="m1/14-certificates",
            certificate_types=(
                CertificateType.CPP,
                CertificateType.GMP,
                CertificateType.CEP,
                CertificateType.COA,
                CertificateType.FREE_SALE,
                CertificateType.TRADEMARK,
                CertificateType.MANUFACTURING_LICENCE,
            ),
        ),
        Module1Slot(
            slot_id="declarations",
            title="Declarations",
            folder="m1/15-declarations",
            declaration_types=(
                DeclarationType.POWER_OF_ATTORNEY,
                DeclarationType.DECLARATION_OF_AUTHENTICITY,
                DeclarationType.GMP_COMPLIANCE_UNDERTAKING,
            ),
        ),
    ],
)

# P09: EU Module 1, per the real EU regional DTD (reference/ectd_dtd/
# eu-regional.dtd -- m1-eu's declared children are m1-0-cover, m1-2-form,
# m1-3-pi, ... no dedicated element for "certificates" or "declarations").
# `app.ectd.regional` maps cover-letter -> m1-0-cover, and folds
# registration-form/certificates/declarations all into m1-2-form (using
# the DTD's own `node-extension` element to give the latter two their own
# titled sub-groups) -- the same bundling real EU filers use, since the
# DTD's `specific` wrapper under m1-2-form is an unstructured leaf/
# node-extension bag beyond that point. This CTD-side profile only needs
# folder placement + which data sources back each slot; the EU element
# mapping itself lives in app.ectd.regional, which is the one module that
# actually needs to know eu-regional.dtd's shape.
EU_PROFILE = RegionProfile(
    region=Region.EU,
    # Deliberately empty, not "none required": the EU has its own Module 1
    # requirements, and they have not been confirmed against the current
    # EMA guidance (AGENTS.md's standing caution about regulator-specific
    # output). Empty preserves exactly today's behaviour -- R13/R16 raised
    # nothing for an EU project before this refactor either -- rather than
    # inventing a requirement list nobody has checked.
    module1_slots=[
        Module1Slot(
            slot_id="cover-letter",
            title="Cover Letter",
            folder="m1/eu/10-cover",
            section_number="1.0",
        ),
        Module1Slot(
            slot_id="registration-form",
            title="Application Form",
            folder="m1/eu/12-administrative-information",
            section_number="1.2",
        ),
        Module1Slot(
            slot_id="certificates",
            title="Certificates",
            folder="m1/eu/12-administrative-information/certificates",
            certificate_types=(
                CertificateType.CPP,
                CertificateType.GMP,
                CertificateType.CEP,
                CertificateType.COA,
                CertificateType.FREE_SALE,
                CertificateType.TRADEMARK,
                CertificateType.MANUFACTURING_LICENCE,
            ),
        ),
        Module1Slot(
            slot_id="declarations",
            title="Declarations",
            folder="m1/eu/12-administrative-information/declarations",
            declaration_types=(
                DeclarationType.POWER_OF_ATTORNEY,
                DeclarationType.DECLARATION_OF_AUTHENTICITY,
                DeclarationType.GMP_COMPLIANCE_UNDERTAKING,
            ),
        ),
    ],
)

# FDA is future work (P09 built EU first -- see the P09 build-log entry
# for the scope call between FDA and EU).
REGION_PROFILES: dict[Region, RegionProfile] = {
    Region.NAFDAC: NAFDAC_PROFILE,
    Region.EU: EU_PROFILE,
}


def get_region_profile(region: Region) -> RegionProfile:
    try:
        return REGION_PROFILES[region]
    except KeyError:
        configured = ", ".join(r.value for r in REGION_PROFILES)
        raise KeyError(f"No CTD region profile configured for {region!r} yet ({configured} only)")
