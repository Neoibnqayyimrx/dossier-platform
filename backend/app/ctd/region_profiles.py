"""Region profile config: Module 1 (P08) and applicability (P17).

Two kinds of regulatory rule live here, for the same reason: both change
when an agency changes its guideline, and both must be re-confirmable
against that guideline by someone reading one file rather than by reading
the builder. Module 1 says WHICH DOCUMENTS a region wants; the applicability
table says WHICH SECTIONS a submission type owes at all.

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

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.models.enums import CertificateType, DeclarationType, Region, SubmissionType
from app.target_toc import TargetLeaf, load_target_leaves

if TYPE_CHECKING:
    from app.models.project import Project


@dataclass(frozen=True)
class Module1Slot:
    slot_id: str
    title: str
    folder: str
    section_number: str | None = None
    certificate_types: tuple[CertificateType, ...] = ()
    declaration_types: tuple[DeclarationType, ...] = ()


@dataclass(frozen=True)
class DocumentSlot:
    """A Module 1 leaf whose content is an UPLOADED file (P18).

    WHY Module 1 uploads need this and Modules 2-5 uploads do not: placement
    for 2-5 is identical across regions, so `app.ctd.structure`'s flat folder
    map serves every profile. Module 1's layout IS the regional part (this
    file's opening docstring), and the same certificate legitimately sits at
    a different number in a different agency's Module 1 -- so which leaf a
    CPP answers is a property of the region, not of the certificate.

    `certificate_type`, when set, is what lets an uploaded file RETIRE a
    placeholder: the builders emit a clearly-marked placeholder for every
    Certificate row on file, and a real document attached at the matching
    leaf makes that placeholder both unnecessary and wrong to ship.
    """

    section_number: str
    title: str
    folder: str
    certificate_type: CertificateType | None = None


@dataclass(frozen=True)
class RegionalInformationItem:
    """One entry of 3.2.R Regional Information (P19).

    WHY this lives in the region profile and not in the section registry,
    unlike every other Module 3 section: 3.2.R is the one part of Module 3
    that is regional BY DEFINITION. ICH M4Q leaves its contents to each
    region -- executed batch records for one authority, a medical-device
    annex for another -- so a common table could only ever hold one
    region's answer and call it the truth. The registry still holds the
    SECTION (it renders like any other); this holds what the section says.

    `guidance` is descriptive, never a regulatory claim: it says where the
    item is expected to come from, so an assessor reading the leaf knows
    what was and was not filed.
    """

    title: str
    guidance: str


class Applicability(str, enum.Enum):
    """What a submission type says about one section (P17).

    Three states, not two, and the third is the interesting one. REQUIRED
    and NOT_APPLICABLE are both settled answers; CONDITIONAL is a QUESTION
    the platform has to put to the filer, because only they know whether
    their drug substance has a CEP or whether they are claiming a biowaiver.
    Modelling it as a third state is what lets rule R19 notice that nobody
    has answered -- the failure mode where a biowaiver claim quietly goes
    missing from a dossier that otherwise validates clean.
    """

    REQUIRED = "required"
    CONDITIONAL = "conditional"
    NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True)
class SectionApplicability:
    """One row of the applicability table: what this submission type says
    about one section number."""

    number: str
    module: int
    title: str
    status: Applicability
    # How the leaf comes into existence, per the target TOC's
    # `production_types`. Carried so the project section list can tell
    # "produced" from "a placeholder standing in for a document nobody has
    # uploaded yet" without a second lookup.
    production: str
    # Set iff status is CONDITIONAL: the yes/no question to put to the filer.
    condition: str | None = None
    # Set iff status is NOT_APPLICABLE: the guideline that makes it so. This
    # string is PRINTED in the statement leaf -- a declaration of
    # inapplicability with no citation is just an absence with a covering
    # note, which is what P17 exists to stop.
    citation: str | None = None


@dataclass(frozen=True)
class ResolvedApplicability:
    """A section's applicability for ONE project: the declared row above,
    plus the filer's answer where the row asked a question."""

    section: SectionApplicability
    # None means unanswered. Only meaningful for a CONDITIONAL section.
    answer: bool | None = None

    @property
    def number(self) -> str:
        return self.section.number

    @property
    def is_unanswered_condition(self) -> bool:
        return self.section.status is Applicability.CONDITIONAL and self.answer is None

    @property
    def owes_statement(self) -> bool:
        """True when this project must PRINT a not-applicable statement here.

        Two ways to arrive at one, and treating them identically downstream
        is the point of this whole phase: a section the guideline excludes
        outright, and a conditional section the filer has answered "no" to.
        An unanswered condition owes nothing yet -- silence is not a "no",
        and emitting a statement on the filer's behalf would put a claim in
        the dossier they never made.
        """
        if self.section.status is Applicability.NOT_APPLICABLE:
            return True
        return self.section.status is Applicability.CONDITIONAL and self.answer is False

    @property
    def is_applicable(self) -> bool:
        """Whether the project actually owes this section's real content."""
        if self.section.status is Applicability.REQUIRED:
            return True
        return self.section.status is Applicability.CONDITIONAL and self.answer is True


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

    # P17: submission type -> section number -> what this filing says about
    # that section.
    #
    # WHY here, beside module1_slots, rather than in the section registry:
    # for exactly the reason recorded at the top of this file. Applicability
    # is a REGULATORY rule ("NAFDAC excuses a multisource filing from Module
    # 4"), it changes when an agency changes its guideline, and it must be
    # re-confirmable against that guideline by someone reading one file. The
    # registry answers a different question -- "what can this platform
    # render" -- and conflating the two is what made applicability implicit
    # in which sections happened to be registered.
    #
    # Empty for a region whose applicability has not been established (EU
    # today), which means "not modelled", not "everything is required" --
    # same convention as the required_* lists above.
    applicability: dict[SubmissionType, dict[str, SectionApplicability]] = field(
        default_factory=dict
    )

    # P18: Module 1 leaves that accept an uploaded document. Empty for a
    # region whose Module 1 has not been modelled (EU), which means "we do
    # not know where these go", not "they cannot be uploaded".
    document_slots: tuple[DocumentSlot, ...] = ()

    # P19: what this region asks for at 3.2.R. Empty means "this region
    # declares no additional regional information", which the rendered leaf
    # says in as many words rather than shipping a blank page -- an empty
    # 3.2.R reads to an assessor as a packaging failure, exactly as an empty
    # Module 4 folder does (P17's reasoning, applied one section down).
    regional_information: tuple[RegionalInformationItem, ...] = ()

    def document_slot(self, section_number: str) -> DocumentSlot | None:
        return next(
            (slot for slot in self.document_slots if slot.section_number == section_number),
            None,
        )

    def applicability_for(self, submission_type: SubmissionType) -> dict[str, SectionApplicability]:
        return self.applicability.get(submission_type, {})


# The guideline the source dossier cites three times to scope itself out of
# Modules 2.4-2.7, Module 4, and everything in 5.3 except 5.3.1.
#
# Matched as a PREFIX, not compared for equality: the YAML spells the same
# citation two ways -- "...multisource (generic) pharmaceutical products"
# for Modules 2 and 4, and "...multisource -- only 5.3.1 applicable" for
# Module 5, because the Module 5 statement says something more specific.
# Equality here silently left all six Module 5 leaves excused in a filing
# that owes them, which is the failure this comment exists to prevent.
MULTISOURCE_GUIDELINE_PREFIX = "NAFDAC guidelines for multisource"


def _multisource_applicability() -> dict[str, SectionApplicability]:
    """The NAFDAC multisource table, read from `docs/target-toc.yaml`.

    Read, not retyped: the contract already records `applicable`,
    `condition` and `not_applicable_reason` for all 98 leaves, and a
    hand-copied second table would be a second truth about what a dossier
    owes. See app/target_toc.py for why that file is allowed to be config.
    """
    table: dict[str, SectionApplicability] = {}
    for leaf in load_target_leaves():
        table[leaf.number] = SectionApplicability(
            number=leaf.number,
            module=leaf.module,
            title=leaf.title,
            status=_status_of(leaf),
            production=leaf.production,
            condition=leaf.condition,
            citation=leaf.not_applicable_reason,
        )
    return table


def _status_of(leaf: TargetLeaf) -> Applicability:
    if leaf.applicable == "conditional":
        return Applicability.CONDITIONAL
    return Applicability.REQUIRED if leaf.applicable == "true" else Applicability.NOT_APPLICABLE


def _excused_only_because_it_is_generic(section: SectionApplicability) -> bool:
    """Is this leaf excused BY THE MULTISOURCE GUIDELINE specifically?

    The qualifier matters: a leaf could in future be not applicable for some
    other reason (a dosage form with no dissolution test, say), and that
    exclusion would still hold for a new chemical entity. Only exclusions
    that exist because the product is a generic get promoted.
    """
    return section.status is Applicability.NOT_APPLICABLE and (section.citation or "").startswith(
        MULTISOURCE_GUIDELINE_PREFIX
    )


def _new_chemical_entity_applicability() -> dict[str, SectionApplicability]:
    """The same section list, scoped for a full (non-generic) application.

    DERIVED from the multisource table by promoting exactly the leaves the
    multisource guideline excuses -- Modules 2.4-2.7, Module 4, and 5.3.2-
    5.3.7 -- back to REQUIRED. A new chemical entity has no comparator to be
    equivalent to, so it owes the nonclinical and clinical evidence in full.

    WHY derive rather than hand-author a second full table: the derivation
    states the ONE regulatory fact that distinguishes the two submission
    types, and cannot drift from the multisource table when a leaf is added.
    A hand-written 98-row twin would drift the first time someone edited one
    of them.

    WHY this deliberately stops there, rather than modelling an NCE filing
    properly: nobody has confirmed the rest against NAFDAC's guidance for
    full applications, and the honest scope of this entry is "prove the seam
    works, and be obviously incomplete rather than quietly wrong" -- the same
    call EU_PROFILE's empty requirement lists already make. It exists so the
    day an NCE or an FDA filing arrives there is a switch to flip.
    """
    table: dict[str, SectionApplicability] = {}
    for number, section in _multisource_applicability().items():
        if _excused_only_because_it_is_generic(section):
            # A promoted leaf is REQUIRED and, being applicable, owes real
            # content rather than a statement -- so its production type is
            # no longer `na_statement`. Saying so here is what stops the
            # section list offering a "produced" tick for a statement that
            # this submission type must not print.
            section = SectionApplicability(
                number=section.number,
                module=section.module,
                title=section.title,
                status=Applicability.REQUIRED,
                production="uploaded",
                condition=None,
                citation=None,
            )
        table[number] = section
    return table


# The NAFDAC Module 1 leaves that hold a third-party document, with the
# folder each lands in and (where there is one) the Certificate row it
# satisfies. Numbers and titles come from the filed dossier the target TOC
# was derived from.
NAFDAC_DOCUMENT_SLOTS: tuple[DocumentSlot, ...] = (
    DocumentSlot(
        section_number="1.2.3",
        title="Certificate of incorporation",
        folder="m1/14-certificates",
        certificate_type=CertificateType.INCORPORATION,
    ),
    DocumentSlot(
        section_number="1.2.7",
        title="Certificate of Pharmaceutical Product (CPP)",
        folder="m1/14-certificates",
        certificate_type=CertificateType.CPP,
    ),
    DocumentSlot(
        section_number="1.2.8",
        title="Certificate of Good Manufacturing Practice",
        folder="m1/14-certificates",
        certificate_type=CertificateType.GMP,
    ),
    DocumentSlot(
        section_number="1.2.9",
        title="Manufacturing Authorization",
        folder="m1/14-certificates",
        certificate_type=CertificateType.MANUFACTURING_LICENCE,
    ),
    DocumentSlot(
        section_number="1.2.10",
        title="Evidence of trademark registration",
        folder="m1/14-certificates",
        certificate_type=CertificateType.TRADEMARK,
    ),
    DocumentSlot(
        section_number="1.2.11",
        title="Superintendent Pharmacist's Annual Licence to Practice",
        folder="m1/14-certificates",
        certificate_type=CertificateType.PHARMACIST_LICENCE,
    ),
    DocumentSlot(
        section_number="1.2.12",
        title="Certificate of Registration and Retention of Premises",
        folder="m1/14-certificates",
        certificate_type=CertificateType.PREMISES_REGISTRATION,
    ),
    DocumentSlot(
        section_number="1.2.13",
        title="Evidence of previous market authorization",
        folder="m1/12-administrative-information",
    ),
    DocumentSlot(
        section_number="1.2.15",
        title="Certificate of Suitability of the European Pharmacopoeia (CEP)",
        folder="m1/14-certificates",
        certificate_type=CertificateType.CEP,
    ),
    DocumentSlot(
        section_number="1.2.16",
        title="Letter of Access for APIMF(s)",
        folder="m1/12-administrative-information",
    ),
    DocumentSlot(
        section_number="1.5",
        title="Electronic Review Documents",
        folder="m1/15-electronic-review-documents",
    ),
)


# NAFDAC's 3.2.R, per the WHO/ICH CTD structure NAFDAC's guideline adopts.
# CAUTION, and the same one the target TOC's `confirmed_against_guideline:
# null` records: this list has not been re-confirmed against NAFDAC's
# current guidance. It is config precisely so that confirming it is an edit
# to one table rather than a change to the builder.
NAFDAC_REGIONAL_INFORMATION: tuple[RegionalInformationItem, ...] = (
    RegionalInformationItem(
        title="Executed production documents",
        guidance=(
            "The executed batch manufacturing record for the batches described in "
            "3.2.P.3.2 and 3.2.P.5.4, filed with this application."
        ),
    ),
    RegionalInformationItem(
        title="Analytical procedures and validation information",
        guidance=(
            "Cross-reference: the procedures are stated in 3.2.S.4.2 and 3.2.P.5.2, "
            "and their validation in 3.2.S.4.3 and 3.2.P.5.3."
        ),
    ),
)


NAFDAC_PROFILE = RegionProfile(
    region=Region.NAFDAC,
    document_slots=NAFDAC_DOCUMENT_SLOTS,
    regional_information=NAFDAC_REGIONAL_INFORMATION,
    applicability={
        SubmissionType.MULTISOURCE_GENERIC: _multisource_applicability(),
        SubmissionType.NEW_CHEMICAL_ENTITY: _new_chemical_entity_applicability(),
    },
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
                # P18: a slot that does not ACCEPT a certificate type is a
                # certificate with nowhere to be filed. Adding members to the
                # enum without adding them here would have left three of them
                # unfileable -- which is exactly what
                # test_nafdac_profile_covers_every_certificate_and_declaration_type
                # exists to catch, and did.
                CertificateType.INCORPORATION,
                CertificateType.PHARMACIST_LICENCE,
                CertificateType.PREMISES_REGISTRATION,
                # P19: the supplier's TSE/BSE certificate for an excipient
                # of animal origin, which rule R21 requires before export.
                CertificateType.TSE_BSE,
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
                # P18: a slot that does not ACCEPT a certificate type is a
                # certificate with nowhere to be filed. Adding members to the
                # enum without adding them here would have left three of them
                # unfileable -- which is exactly what
                # test_nafdac_profile_covers_every_certificate_and_declaration_type
                # exists to catch, and did.
                CertificateType.INCORPORATION,
                CertificateType.PHARMACIST_LICENCE,
                CertificateType.PREMISES_REGISTRATION,
                # P19: the supplier's TSE/BSE certificate for an excipient
                # of animal origin, which rule R21 requires before export.
                CertificateType.TSE_BSE,
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


def resolve_applicability(project: "Project") -> dict[str, ResolvedApplicability]:
    """What THIS project says about every section, in target-TOC order.

    The join between two things that are each meaningless alone: the region
    profile's declared table (a regulatory rule) and the project's own
    answers to the conditional questions (a filing decision only the filer
    can make).

    Everything downstream reads this and nothing re-derives it --
    `app.templating.instances` to decide which statement leaves to emit,
    rules R18/R19 to complain, and the project section list to draw the
    screen. One resolution, three readers, no chance of the built package
    and the screen describing different dossiers.
    """
    try:
        profile = get_region_profile(project.region)
    except KeyError:
        # WHY this swallows what `get_region_profile` deliberately raises:
        # the raise exists for BUILDERS -- asking an unconfigured region to
        # produce a package must fail loudly rather than emit a guess. This
        # function is also called by the validation rules, which run on every
        # project including one targeting a region nobody has modelled yet
        # (FDA today). "No profile" and "an empty table" mean the same thing
        # to a reader of applicability: nothing is declared, so nothing is
        # claimed -- exactly what EU_PROFILE's empty table already says. An
        # unmodelled region must not make readiness crash.
        return {}

    answers = project.condition_answers or {}
    return {
        number: ResolvedApplicability(section=section, answer=answers.get(number))
        for number, section in profile.applicability_for(project.submission_type).items()
    }


def satisfied_certificate_types(project: "Project") -> set[CertificateType]:
    """Certificate types this project has attached a REAL document for (P18).

    The join between two things that never used to meet: a `Certificate`
    row, which is metadata about a document someone must go and obtain, and
    a `SectionDocument`, which is that document having arrived. The region
    profile is what knows they are the same thing, because it is what knows
    a CPP answers leaf 1.2.7 in a NAFDAC filing.

    Used by both builders to stop emitting a placeholder once the real file
    exists, and by rule R20 to refuse to export while one has not.
    """
    profile = REGION_PROFILES.get(project.region)
    if profile is None:
        return set()

    attached = {document.section_number for document in project.documents}
    return {
        slot.certificate_type
        for slot in profile.document_slots
        if slot.certificate_type is not None and slot.section_number in attached
    }
