"""Concrete rules, each derived from a real feature (or real bug) of the LAMOX
dossier. See reference/worked-example-lamox.md for the provenance of each.

Note on approach: R01-R03 scan section narrative text. Here we use simple regex
scanning, which is honest for a slice. In production these run against the
STRUCTURED template data (P04) so there's far less free text to scan — the
determinism boundary means numbers should live in data slots, not prose. The
scanning rules are the safety net for prose that slips through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.ctd.region_profiles import (
    REGION_PROFILES,
    Applicability,
    get_region_profile,
    resolve_applicability,
    satisfied_certificate_types,
)
from app.models.bioequivalence import BiowaiverKind
from app.models.stability import supported_months
from app.narrative.guardrails import check_patient_register
from app.templating.context import build_context
from app.validation.acceptance import evaluate
from app.validation.engine import Finding, Severity, rule
from app.models import (
    DECLARATIONS_REQUIRING_NOTARIZATION,
    TSE_RELEVANT_ORIGINS,
    CertificateType,
    DosageForm,
    GMPStatus,
    ManufacturerRole,
    PackagingComponent,
    PackagingRole,
    Region,
    StabilityStudyType,
    SubmissionType,
)

# Words that denote a dosage form, mapped to the enum member they imply.
# Deliberately excludes ambiguous words ("drops" alone could mean eye or
# ear) -- a wrong mapping here would make R02 flag mismatches that aren't
# real, which is worse than missing a real one.
_FORM_WORDS = {
    "tablet": DosageForm.TABLET,
    "tablets": DosageForm.TABLET,
    "capsule": DosageForm.CAPSULE_HARD,
    "capsules": DosageForm.CAPSULE_HARD,
    "syrup": DosageForm.SYRUP,
    "suspension": DosageForm.SUSPENSION,
    "suspensions": DosageForm.SUSPENSION,
    "injection": DosageForm.INJECTION,
    "infusion": DosageForm.INFUSION,
    "cream": DosageForm.CREAM,
    "ointment": DosageForm.OINTMENT,
    "gel": DosageForm.GEL,
    "lotion": DosageForm.LOTION,
    "suppository": DosageForm.SUPPOSITORY,
    "suppositories": DosageForm.SUPPOSITORY,
    "pessary": DosageForm.PESSARY,
    "pessaries": DosageForm.PESSARY,
    "lozenge": DosageForm.LOZENGE,
    "lozenges": DosageForm.LOZENGE,
    "granules": DosageForm.GRANULES,
    "elixir": DosageForm.ELIXIR,
    "patch": DosageForm.TRANSDERMAL_PATCH,
    "patches": DosageForm.TRANSDERMAL_PATCH,
}


@rule("R01")
def strength_consistency(project) -> list[Finding]:
    """Every strength stated near an active's name in narrative must equal
    THAT active's declared strength. Catches LAMOX's '250mg' vs 500mg typo
    -- and, for a combination product (e.g. AMPICLOX), a mismatch on ANY
    of its active ingredients, not just the first one. Strength lives on
    ActiveIngredient (not Product) precisely so this loop generalizes to
    N actives without a special case for N=1."""
    product = project.product
    out: list[Finding] = []
    for api in product.apis:
        if api.strength_value is None:
            continue
        declared = float(api.strength_value)
        name = api.inn_name.lower()
        for sec in project.sections:
            text = sec.narrative_text
            # find "<api name> ... <n> mg" mentions, tolerating words in between
            for m in re.finditer(
                rf"{re.escape(name)}[^.\n]{{0,40}}?(\d{{2,5}})\s*mg",
                text,
                flags=re.IGNORECASE,
            ):
                value = float(m.group(1))
                if value != declared:
                    out.append(
                        Finding(
                            "R01",
                            Severity.ERROR,
                            "consistency",
                            f"Section {sec.number} states {api.inn_name} "
                            f"{value:.0f} mg, but the declared strength is "
                            f"{declared:.0f} mg.",
                            section=sec.number,
                        )
                    )
    return out


@rule("R02")
def dosage_form_consistency(project) -> list[Finding]:
    """No section may reference a dosage form other than the product's.
    Catches LAMOX's 'Batch Size: 250,000 Tablets' on a capsule product."""
    product = project.product
    out: list[Finding] = []
    for sec in project.sections:
        for word, implied in _FORM_WORDS.items():
            if re.search(rf"\b{word}\b", sec.narrative_text, flags=re.IGNORECASE):
                if implied is not product.dosage_form:
                    out.append(
                        Finding(
                            "R02",
                            Severity.ERROR,
                            "consistency",
                            f"Section {sec.number} mentions '{word}', implying a "
                            f"{implied.value}, but the product is a "
                            f"{product.dosage_form.value}.",
                            section=sec.number,
                        )
                    )
    return out


@rule("R03")
def cross_product_contamination(project) -> list[Finding]:
    """Flag references to OTHER products' brand names — the fingerprint of a
    dossier copy-pasted from a previous product. Catches the leftover 'LATRIM'
    reference in LAMOX's table-of-contents folder."""
    product = project.product
    own = {product.brand_name.lower(), product.generic_name.lower()}
    # A small registry of known company brands. In production this is the
    # product master list; a foreign brand appearing in this dossier is a leak.
    known_brands = {"latrim", "lamox", "fluxet", "zinc plus", "nuflox"}
    foreign = known_brands - own
    out: list[Finding] = []
    for sec in project.sections:
        for brand in foreign:
            if re.search(rf"\b{re.escape(brand)}\b", sec.narrative_text, re.IGNORECASE):
                out.append(
                    Finding(
                        "R03",
                        Severity.ERROR,
                        "contamination",
                        f"Section {sec.number} references '{brand.upper()}', a "
                        f"different product. Likely copy-paste from another dossier.",
                        section=sec.number,
                    )
                )
    return out


@rule("R04")
def salt_base_batch_arithmetic(project) -> list[Finding]:
    """Reconcile each active batch-formula line's declared quantity against
    ITS OWN active ingredient's strength x salt_factor x batch_size --
    correct for a combination product where each active has a different
    salt factor (e.g. AMPICLOX's ampicillin trihydrate vs cloxacillin
    sodium), not just whichever API happens to be first on the product.
    Demonstrates a rule that PASSES on LAMOX (144 kg trihydrate is correct
    for 500 mg base x 250,000)."""
    product = project.product
    out: list[Finding] = []
    for line in product.batch_formula:
        if not line.is_active or line.declared_batch_qty_kg is None:
            continue
        api = line.active_ingredient
        if api is None and len(product.apis) == 1:
            api = product.apis[0]  # single-API product, unambiguous
        if api is None:
            continue  # can't reconcile without knowing which API this line is
        salt_factor = float(api.salt_factor)
        base_mg = float(line.qty_per_unit_mg)  # per-unit base mg
        units = int(line.batch_size_units)
        computed_kg = base_mg * salt_factor * units / 1_000_000  # mg -> kg
        declared_kg = float(line.declared_batch_qty_kg)
        tolerance = 0.02  # 2%
        if declared_kg and abs(computed_kg - declared_kg) / declared_kg > tolerance:
            out.append(
                Finding(
                    "R04",
                    Severity.WARNING,
                    "arithmetic",
                    f"Batch quantity for {line.component}: declared {declared_kg:.1f} kg "
                    f"but strength x salt factor x batch size gives {computed_kg:.1f} kg "
                    f"(>2% off).",
                )
            )
    return out


@rule("R05")
def shelf_life_within_stability(project) -> list[Finding]:
    """A claimed shelf life (or retest period) must be within the longest
    timepoint at which the long-term study still met every acceptance
    criterion. ERROR -- it blocks the export.

    **P21 upgraded this rule, and the upgrade is the point of the phase.**
    Until now it compared the claim against `duration_months`: how long the
    study RAN. That could only ever catch a claim longer than the study,
    and it read a 24-month study that failed dissolution at 6 months as 24
    months of support -- the arithmetic was right and the question was
    wrong. It now compares against `longest_passing_timepoint`, which is
    computed from the timepoint results against the specification's own
    limits (app/models/stability.py).

    Two other things changed with it, both of which were latent bugs:

    - **It only counts LONG-TERM studies now.** The old `max()` ran over
      every study on file, so a 6-month accelerated study counted as six
      months of shelf-life support. It is not -- accelerated data supports
      excursions and extrapolation, never the shelf life itself (ICH
      Q1A(R2) 2.2.7). R24 says so separately.
    - **It reaches the drug substance too.** A retest period is the
      substance's exact analogue of a shelf life, justified by 3.2.S.7
      data, and before P21 a study could not belong to a substance at all.

    Silent when nothing is claimed: a product with no shelf life on file
    yet is R06/R07-style completeness territory, not this rule's job.
    """
    out: list[Finding] = []
    for claim in _stability_claims(project):
        if claim.months is None:
            continue
        long_term = [
            study
            for study in claim.owner.stability
            if study.study_type is StabilityStudyType.LONG_TERM
        ]
        supported, basis = supported_months(long_term)
        if claim.months <= supported:
            continue
        out.append(
            Finding(
                "R05",
                Severity.ERROR,
                "consistency",
                f"{claim.label} of {_owner_label(claim.owner)} is {claim.months} months, "
                f"but the long-term stability data supports {supported} months ({basis}).",
                section=claim.data_section,
            )
        )
    return out


@rule("R06")
def generic_requires_one_bioequivalence_route(project) -> list[Finding]:
    """A multisource filing must take EXACTLY ONE bioequivalence route.

    **P22 rewrote this rule, and the rewrite is what the phase unlocks.**
    Until now it asked whether a `ClinicalEntry` row of kind
    "bioequivalence" existed -- which is the most a free-text summary can
    be asked. It could not tell an in vivo study from a biowaiver, could
    not notice that both had been filed, and could not read a single
    number out of either.

    The regulatory fact it now enforces: there are two ways for a generic
    to show it behaves like the comparator, and they are ALTERNATIVES.
    Either a human study was run (5.3.1.2), or a waiver is claimed on
    biopharmaceutic grounds (1.2.17) or on proportionality with a strength
    that was studied (1.2.18). **Neither** is an incomplete dossier.
    **Both** is a contradiction: the application says at once that a study
    was necessary and that it was not, and an assessor reading Module 1
    against Module 5 finds two different accounts of the same product.

    ## Why the claim is read from the applicability answers

    P17 made "is a biowaiver being claimed?" a question the filer answers,
    because only they can. That answer is what makes leaf 1.2.17 applicable
    and puts the request in the package -- so it is also what this rule has
    to read. Reading a `Biowaiver` row instead would let the row exist
    while the leaf stays out of the dossier, which is a filing where the
    platform believes a claim the regulator never sees.

    ## Scope

    Multisource filings only. A new chemical entity has no comparator to be
    equivalent to; asking it for a bioequivalence route would be asking the
    wrong question of the whole application. Before P22 this rule fired on
    every project regardless, which was wrong in a way nothing noticed
    because nothing had built an NCE filing yet.
    """
    if project.submission_type is not SubmissionType.MULTISOURCE_GENERIC:
        return []

    product = project.product
    applicability = resolve_applicability(project)
    studies = list(product.bioequivalence_studies)
    claimed = {
        kind: (applicability.get(number) is not None and applicability[number].answer is True)
        for kind, number in (
            (BiowaiverKind.BCS_BASED, "1.2.17"),
            (BiowaiverKind.ADDITIONAL_STRENGTH, "1.2.18"),
        )
    }
    claimed_kinds = [kind for kind, yes in claimed.items() if yes]

    out: list[Finding] = []

    if not studies and not claimed_kinds:
        out.append(
            Finding(
                "R06",
                Severity.ERROR,
                "completeness",
                "This multisource filing shows no bioequivalence route: there is no in "
                "vivo study on file (5.3.1.2) and no biowaiver has been claimed (1.2.17 "
                "or 1.2.18). Exactly one of the two is required.",
                section="5.3.1.2",
            )
        )

    if studies and claimed_kinds:
        # WHY the STUDY is named and not just "a study": with one Project
        # per strength, "the same strength" is this whole filing, so the
        # filer needs to be told which of the two claims to withdraw.
        names = ", ".join(sorted(study.study_identifier for study in studies))
        for kind in claimed_kinds:
            number = "1.2.17" if kind is BiowaiverKind.BCS_BASED else "1.2.18"
            out.append(
                Finding(
                    "R06",
                    Severity.ERROR,
                    "consistency",
                    f"A {kind.value} biowaiver is claimed at {number} AND an in vivo "
                    f"bioequivalence study is filed for the same strength ({names}). "
                    f"The two routes are mutually exclusive -- withdraw the biowaiver "
                    f"claim or remove the study.",
                    section=number,
                )
            )

    # A claim with no request data behind it. ERROR rather than a warning:
    # the leaf IS in the package (the answer is what put it there), and it
    # would ship as a request naming no strength and citing no evidence.
    for kind in claimed_kinds:
        number = "1.2.17" if kind is BiowaiverKind.BCS_BASED else "1.2.18"
        if not any(waiver.kind is kind for waiver in product.biowaivers):
            out.append(
                Finding(
                    "R06",
                    Severity.ERROR,
                    "completeness",
                    f"A {kind.value} biowaiver is claimed at {number}, but no biowaiver "
                    f"request data is on file -- the leaf would ship with nothing in it.",
                    section=number,
                )
            )

    # The mirror: data entered, claim never made. WARNING, not ERROR --
    # nothing incorrect is being filed, but a request the filer believes
    # they have made is silently absent from the package, which is a
    # failure they would otherwise discover from the agency.
    for waiver in product.biowaivers:
        if not claimed[waiver.kind]:
            out.append(
                Finding(
                    "R06",
                    Severity.WARNING,
                    "completeness",
                    f"A {waiver.kind.value} biowaiver request is on file for "
                    f"{waiver.strength}, but {waiver.section_number} has not been "
                    f"answered 'yes', so the request will not be in the package.",
                    section=waiver.section_number,
                )
            )

    return out


@rule("R07")
def api_specification_present(project) -> list[Finding]:
    """Every active ingredient must have a specification on file
    (Module 3.2.S.4.1) -- completeness, not just "the row exists".

    Reads the specification TABLE now, not the old free-text field: a
    specification with no test rows cannot be rendered as 3.2.S.4.1
    requires, so an empty list is the same failure as the field being
    absent used to be."""
    out: list[Finding] = []
    for api in project.product.apis:
        if not api.specification:
            out.append(
                Finding(
                    "R07",
                    Severity.ERROR,
                    "completeness",
                    f"{api.inn_name} has no specification on file (required, Module 3.2.S.4.1).",
                )
            )
    return out


@rule("R08")
def manufacturer_gmp_certified(project) -> list[Finding]:
    """Every manufacturer's GMP status must be CERTIFIED -- pending,
    expired, not-certified, or simply not on file all block export."""
    out: list[Finding] = []
    for manufacturer in project.product.manufacturers:
        if manufacturer.gmp_status != GMPStatus.CERTIFIED:
            status = manufacturer.gmp_status.value if manufacturer.gmp_status else "not on file"
            out.append(
                Finding(
                    "R08",
                    Severity.ERROR,
                    "completeness",
                    f"Manufacturer {manufacturer.name}'s GMP status is '{status}', not certified.",
                )
            )
    return out


@rule("R09")
def api_manufacturer_role_integrity(project) -> list[Finding]:
    """An API's linked manufacturer, if any, must actually play the
    API_MANUFACTURER role. A foreign key alone only proves the row
    exists -- not that it's the RIGHT kind of row (e.g. not accidentally
    pointed at the finished-product site)."""
    out: list[Finding] = []
    for api in project.product.apis:
        manufacturer = api.manufacturer
        if manufacturer is not None and manufacturer.role != ManufacturerRole.API_MANUFACTURER:
            out.append(
                Finding(
                    "R09",
                    Severity.ERROR,
                    "reference-integrity",
                    f"{api.inn_name} is linked to manufacturer "
                    f"{manufacturer.name}, whose role is "
                    f"'{manufacturer.role.value}', not API manufacturer.",
                )
            )
    return out


# ICH Q3C residual-solvent class limits (ppm) -- public, numeric-only
# reference data, never the guideline's own text (same copyright-safe
# principle as the P03 knowledge base's ICH allowlist). A short,
# representative subset, not the full class 1-3 table.
_Q3C_LIMITS_PPM = {
    "methanol": 3000,
    "dichloromethane": 600,
    "chloroform": 60,
    "acetonitrile": 410,
    "pyridine": 200,
    "toluene": 890,
}

_SOLVENT_MENTION_RE = re.compile(r"([A-Za-z][A-Za-z ]*?)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*ppm")


@rule("R10")
def residual_solvent_limits(project) -> list[Finding]:
    """Flag a residual solvent level above its ICH Q3C class limit.
    WARNING, not ERROR: parsing free text for "<solvent> <n> ppm" mentions
    is heuristic, and a parsing miss shouldn't silently pass while a
    parsing false-positive shouldn't hard-block a real submission --
    a human reviews every warning either way."""
    out: list[Finding] = []
    for api in project.product.apis:
        if not api.residual_solvents:
            continue
        for match in _SOLVENT_MENTION_RE.finditer(api.residual_solvents):
            solvent = match.group(1).strip().lower()
            limit = _Q3C_LIMITS_PPM.get(solvent)
            if limit is None:
                continue
            level = float(match.group(2))
            if level > limit:
                out.append(
                    Finding(
                        "R10",
                        Severity.WARNING,
                        "regulatory-limit",
                        f"{api.inn_name}: {solvent} at {level:g} ppm exceeds "
                        f"the ICH Q3C limit of {limit} ppm.",
                    )
                )
    return out


@rule("R11")
def pharmacopoeial_version_reminder(project) -> list[Finding]:
    """INFO reminder: any compendial-standard citation should be checked
    against its CURRENT edition before submission. Pharmacopoeia text is
    never stored here at all (AGENTS.md §5) -- only the citation -- so
    this is a nudge for a human to go verify, not something code can
    check on its own."""
    product = project.product
    out: list[Finding] = []
    for api in product.apis:
        if api.compendial_std is not None:
            out.append(
                Finding(
                    "R11",
                    Severity.INFO,
                    "regulatory-limit",
                    f"{api.inn_name} cites {api.compendial_std.value} -- "
                    f"verify the current edition is in force before submission.",
                )
            )
    for excipient in product.excipients:
        if excipient.compendial_status is not None:
            out.append(
                Finding(
                    "R11",
                    Severity.INFO,
                    "regulatory-limit",
                    f"{excipient.name} cites {excipient.compendial_status.value} "
                    f"-- verify the current edition is in force before submission.",
                )
            )
    # P20: impurity limits, which are the limits most likely to MOVE between
    # editions -- a monograph revision that adds a named impurity or tightens
    # an individual limit changes what the applicant has committed to, and
    # nothing in the dossier announces it. The reminder can only be raised
    # because `Impurity.limit_source` records the citation as data; the
    # platform still stores no monograph text (AGENTS.md §5).
    for owner in [*product.apis, product]:
        for impurity in owner.impurities:
            if not _cites_a_pharmacopoeia(impurity.limit_source):
                continue
            out.append(
                Finding(
                    "R11",
                    Severity.INFO,
                    "regulatory-limit",
                    f"Impurity {impurity.name} ({_owner_label(owner)}) takes its limit "
                    f"of {impurity.limit or 'not stated'} from {impurity.limit_source} "
                    f"-- verify the current edition is in force before submission.",
                    section="3.2.S.3.2" if owner is not product else "3.2.P.5.5",
                )
            )
    return out


# The pharmacopoeias a limit can be sourced from, as they are actually
# cited. Narrow on purpose: R11 is an INFO reminder, and a false positive
# here costs a line of noise, but the LIST is also what decides whether an
# in-house limit is silently treated as compendial, which would tell the
# filer to go check a monograph that does not govern their limit.
_PHARMACOPOEIA_TOKENS = ("bp", "usp", "ph. eur", "ph eur", "ep", "jp", "monograph")


def _cites_a_pharmacopoeia(limit_source: str | None) -> bool:
    if not limit_source:
        return False
    # Tokenised rather than substring-matched: "ep" is inside "except" and
    # inside "development", and matching those would attach a
    # pharmacopoeial reminder to an in-house toxicological justification.
    words = re.findall(r"[a-z.]+", limit_source.lower())
    text = limit_source.lower()
    return any(token in words for token in _PHARMACOPOEIA_TOKENS) or any(
        token in text for token in ("ph. eur", "ph eur", "monograph")
    )


def _owner_label(owner) -> str:
    """What a specification owner is called, for a finding's message. A
    finding must name the offending values (see Finding.message), and
    "Impurity A" alone does not say whose impurity A."""
    for attribute in ("inn_name", "brand_name", "name"):
        value = getattr(owner, attribute, None)
        if value:
            return str(value)
    return "unknown material"


_PACKAGING_LABEL_COMPONENTS = (
    PackagingComponent.ARTWORK,
    PackagingComponent.LABEL,
    PackagingComponent.CARTON,
)


@rule("R12")
def pack_size_matches_packaging(project) -> list[Finding]:
    """The product's declared pack size should appear in at least one
    artwork/label/carton packaging description -- a mismatch usually
    means the artwork wasn't updated when the pack size changed."""
    product = project.product
    if not product.pack_size:
        return []
    # P19: the drug substance's own packaging is excluded. An API drum's
    # label is not where the finished product's pack size is printed, and
    # once `role` existed, leaving it out of this filter would have let a
    # drum silently satisfy -- or silently fail -- a check about the
    # medicine's carton.
    relevant = [
        p
        for p in product.packaging
        if p.component in _PACKAGING_LABEL_COMPONENTS and p.role is not PackagingRole.DRUG_SUBSTANCE
    ]
    if not relevant:
        return []
    if any(product.pack_size.lower() in (p.description or "").lower() for p in relevant):
        return []
    return [
        Finding(
            "R12",
            Severity.WARNING,
            "consistency",
            f"Declared pack size '{product.pack_size}' is not mentioned in "
            f"any artwork/label/carton packaging description.",
        )
    ]


@rule("R13")
def required_certificates_present(project) -> list[Finding]:
    """Every certificate the project's region requires must be on file AND
    unexpired. For NAFDAC that is the Certificate of Pharmaceutical Product
    (CPP).

    WHY the requirement is read from the region profile rather than
    hard-coded here (P15a): it was previously stated in this rule and
    would have needed a second copy in the frontend to know which Module 1
    fields to ask for. A region whose profile declares no required
    certificates raises nothing, which is exactly what this rule did for
    EU projects when it was region-scoped instead."""
    profile = REGION_PROFILES.get(project.region)
    if profile is None:
        return []

    # P18 rephrased this rule from "is there a metadata row" to "is there a
    # metadata row AND, eventually, a document". The row half still lives
    # here (it is what carries the expiry date a regulator checks); the
    # document half is R20, deliberately separate so the two failures read
    # differently: "you have not obtained the CPP yet" and "you obtained it
    # but never attached the file" are different problems for different
    # people on different days.
    satisfied = satisfied_certificate_types(project)

    out: list[Finding] = []
    for required in profile.required_certificate_types:
        held = [c for c in project.product.certificates if c.certificate_type == required]
        if not held and required not in satisfied:
            out.append(
                Finding(
                    "R13",
                    Severity.ERROR,
                    "completeness",
                    f"No {required.value} certificate on file -- required for a "
                    f"{project.region.value} filing.",
                )
            )
        elif not any(c.expiry_date is not None and c.expiry_date >= date.today() for c in held):
            out.append(
                Finding(
                    "R13",
                    Severity.ERROR,
                    "completeness",
                    f"The {required.value} certificate on file is expired or has "
                    f"no expiry date recorded.",
                )
            )
    return out


@rule("R14", regions=[Region.NAFDAC])
def nafdac_applicant_required(project) -> list[Finding]:
    """A NAFDAC filing must name who is legally applying (Module 1's
    opening question -- dossier-anatomy.md) -- region-scoped like R13,
    since a different region's Module 1 has its own applicant-equivalent
    requirement, not necessarily this exact check."""
    if project.applicant is None:
        return [
            Finding(
                "R14",
                Severity.ERROR,
                "completeness",
                "No applicant on file -- a NAFDAC filing must name the "
                "legal entity submitting the application.",
            )
        ]
    return []


@rule("R15")
def declarations_signed(project) -> list[Finding]:
    """Any Declaration attached to the project (Power of Attorney,
    Declaration of Authenticity, GMP undertaking) must actually be signed
    before export -- an unsigned one is worse than a missing one, since it
    looks complete at a glance. Notarization is a softer nudge (WARNING):
    only some declaration types require it (DECLARATIONS_REQUIRING_
    NOTARIZATION), and a human should double-check rather than have this
    hard-block a filing whose real requirement this engine can't verify."""
    out: list[Finding] = []
    for declaration in project.declarations:
        label = declaration.declaration_type.value
        if not declaration.signed:
            out.append(
                Finding(
                    "R15",
                    Severity.ERROR,
                    "completeness",
                    f"{label} is on file but not yet signed.",
                )
            )
        elif (
            declaration.declaration_type in DECLARATIONS_REQUIRING_NOTARIZATION
            and not declaration.notarized
        ):
            out.append(
                Finding(
                    "R15",
                    Severity.WARNING,
                    "completeness",
                    f"{label} is signed but not yet notarized/legalized.",
                )
            )
    return out


@rule("R16")
def required_declarations_present(project) -> list[Finding]:
    """Every declaration the region requires must be on file at all --
    distinct from R15, which only checks that whatever declarations ARE
    attached are signed. A project with zero declarations passes R15
    vacuously but must fail here.

    Requirements come from the region profile, same as R13's."""
    profile = REGION_PROFILES.get(project.region)
    if profile is None:
        return []
    present = {d.declaration_type for d in project.declarations}
    missing = [t for t in profile.required_declaration_types if t not in present]
    if missing:
        names = ", ".join(t.value for t in missing)
        return [
            Finding(
                "R16",
                Severity.ERROR,
                "completeness",
                f"Missing required declaration(s) for a "
                f"{project.region.value} filing: {names}.",
            )
        ]
    return []


@rule("R17")
def drug_substance_manufacturer_named(project) -> list[Finding]:
    """Every active ingredient must name its manufacturer.

    Not a house style rule -- the ICH eCTD DTD declares
    `m3-2-s-drug-substance` with `substance` AND `manufacturer` both
    #REQUIRED, so a nameless drug substance cannot produce a valid
    backbone at all. Caught here, at the data layer, rather than at a
    gateway: the point of P06 is that the applicant learns this while
    they can still fix it.
    """
    out: list[Finding] = []
    for api in project.product.apis:
        if api.manufacturer is None:
            out.append(
                Finding(
                    "R17",
                    Severity.ERROR,
                    "completeness",
                    f"{api.inn_name} has no manufacturer on file (required for "
                    f"Module 3.2.S; the eCTD backbone cannot name the substance without it).",
                )
            )
    return out


@rule("R18")
def not_applicable_section_has_no_content(project) -> list[Finding]:
    """A section declared NOT APPLICABLE must not also carry content (P17).

    This is a contradiction the dossier itself would state out loud: the
    package would contain both a page saying "Module 4 is not applicable per
    the multisource guideline" and Module 4 material. An assessor reading
    both cannot tell which one the applicant means, and the charitable
    reading -- that the statement is boilerplate nobody checked -- damages
    every other declaration in the filing.

    ERROR rather than WARNING for that reason: it is not an omission, it is
    a self-contradiction, and the applicant has to decide which of the two
    is true before this can be exported.
    """
    applicability = resolve_applicability(project)
    out: list[Finding] = []
    for section in project.sections:
        resolved = applicability.get(section.number)
        if resolved is None or not resolved.owes_statement:
            continue
        if not (section.narrative_text or "").strip():
            continue
        basis = (
            f"declared not applicable ({resolved.section.citation})"
            if resolved.section.status is Applicability.NOT_APPLICABLE
            else f"answered 'no' to the condition: {resolved.section.condition}"
        )
        out.append(
            Finding(
                "R18",
                Severity.ERROR,
                "applicability",
                f"Section {section.number} is {basis}, but content is on file for it. "
                f"A dossier cannot both exclude a section and fill it -- remove the "
                f"content, or change the section's applicability.",
                section=section.number,
            )
        )
    return out


@rule("R19")
def conditional_sections_are_answered(project) -> list[Finding]:
    """Every CONDITIONAL section needs a yes/no from the filer (P17).

    WARNING, not ERROR, and the distinction is the whole point. Only the
    applicant knows whether their drug substance is covered by a CEP or
    whether they are claiming a biowaiver; the platform cannot compute it,
    and refusing to export until every question is answered would make an
    unrelated filing unshippable over a question that genuinely does not
    apply. But silence must not be invisible either -- an unanswered 1.2.17
    is exactly how a biowaiver claim goes quietly missing from a dossier
    that otherwise validates clean, and the applicant discovers it from the
    agency rather than from us.

    So: surfaced on every readiness check, never a gate.
    """
    return [
        Finding(
            "R19",
            Severity.WARNING,
            "applicability",
            f"Section {resolved.number} ({resolved.section.title}) is conditional and "
            f"unanswered: {resolved.section.condition}. Answer it -- 'no' files a "
            f"not-applicable statement, 'yes' means the section owes content.",
            section=resolved.number,
        )
        for resolved in resolve_applicability(project).values()
        if resolved.is_unanswered_condition
    ]


@rule("R20")
def no_applicable_leaf_ships_a_placeholder(project) -> list[Finding]:
    """A leaf the dossier owes must not go to a regulator as a placeholder.

    This is the rule P18 exists to make true, and it is the severity model
    working exactly as designed. A placeholder is not an approximation of a
    document -- it is a page that says, in capitals, "PLACEHOLDER — REPLACE
    THIS FILE". Its whole purpose (see app/templating/certificates.py) is to
    make a gap loud rather than silent. Shipping one is therefore not a
    degraded submission; it is submitting a note admitting the submission is
    incomplete, and the agency's response to that is not in doubt.

    ERROR, so it blocks the build. WHY an ERROR and not a WARNING, when R19
    (an unanswered conditional) is only a WARNING: the platform cannot know
    whether a biowaiver is being claimed, but it knows with certainty that
    the CPP is still a placeholder -- it generated the placeholder. A rule
    that is certain about a fatal defect should gate; a rule that is
    guessing should not.

    The deliberate exception path already exists and is unchanged: a human
    can override this with a logged reason (P06/P15c), which is right for
    the real case of a pre-submission meeting package where the certificates
    genuinely are not in yet.
    """
    profile = REGION_PROFILES.get(project.region)
    if profile is None:
        return []

    satisfied = satisfied_certificate_types(project)
    out: list[Finding] = []

    # Every Certificate row on file becomes a placeholder in the package
    # unless a real document has been attached at its leaf. Iterating the
    # ROWS (not the region's required list) is deliberate: a certificate
    # someone chose to record is one they intend to file, and a placeholder
    # for an optional certificate is just as unshippable as one for a
    # mandatory certificate.
    slots_by_type = {
        slot.certificate_type: slot
        for slot in profile.document_slots
        if slot.certificate_type is not None
    }
    outstanding = {c.certificate_type for c in project.product.certificates} - satisfied

    for certificate_type in sorted(outstanding, key=lambda t: t.value):
        slot = slots_by_type.get(certificate_type)
        if slot is None:
            # WHY silence rather than an error here: this region has no
            # declared leaf for that certificate, so there is nowhere to
            # attach it -- and a gate you cannot pass is not a gate, it is a
            # wall. It would block every EU export today with an instruction
            # ("attach the document") the platform gives no way to follow.
            #
            # The gap is real and it is EU Module 1 being unmodelled, which
            # EU_PROFILE already says of itself. It gets fixed by declaring
            # those slots, at which point this rule starts covering EU with
            # no change here.
            continue
        out.append(
            Finding(
                "R20",
                Severity.ERROR,
                "completeness",
                f"The {certificate_type.value} certificate (leaf {slot.section_number}) is "
                f"still a generated placeholder -- attach the actual document before "
                f"exporting.",
                section=slot.section_number,
            )
        )
    return out


@rule("R21")
def animal_origin_excipient_has_tse_evidence(project) -> list[Finding]:
    """An excipient of human or animal origin, with no TSE/BSE certificate.

    The regulatory fact: gelatin, lactose, magnesium stearate and stearic
    acid are routinely of animal origin, and a filing that uses one owes
    evidence that the material complies with the current TSE/BSE guidance --
    which only the material's SUPPLIER can issue. That is why the evidence
    is a `Certificate` (a third party's document) and not a `Declaration`
    (one the applicant signs).

    ERROR, and for R20's reason rather than R19's: the platform is not
    guessing here. The filer has positively declared the origin as animal
    or human, and the certificate is either on file or it is not. A rule
    certain about a fatal defect should gate.

    WHY silence when NO origin is declared at all: an excipient with a null
    origin has not been classified, and this rule cannot tell a synthetic
    material from an unclassified animal one. Erroring there would block
    every legacy project on data nobody has been asked for yet; the honest
    place for that gap is the rendered 3.2.P.4.5 leaf, which names the
    unclassified materials and says the statement does not cover them.

    KNOWN LIMITATION: `Certificate` has no excipient foreign key, so one
    TSE/BSE certificate satisfies every animal-origin excipient on the
    product. A dossier with gelatin capsules and bovine lactose from two
    suppliers owes two certificates and this rule sees one. Recorded in the
    P19 build-log entry; fixing it is a migration, not a rule change.
    """
    of_concern = [e for e in project.product.excipients if e.origin in TSE_RELEVANT_ORIGINS]
    if not of_concern:
        return []
    if any(
        certificate.certificate_type is CertificateType.TSE_BSE
        for certificate in project.product.certificates
    ):
        return []

    named = ", ".join(f"{e.name} ({e.origin.value})" for e in of_concern)
    return [
        Finding(
            "R21",
            Severity.ERROR,
            "completeness",
            f"Excipients of human or animal origin are declared ({named}) but no TSE/BSE "
            f"certificate is on file -- 3.2.P.4.5 cannot make its statement without one.",
            section="3.2.P.4.5",
        )
    ]


@rule("R22")
def batch_results_within_specification(project) -> list[Finding]:
    """A batch analysis result outside its own specification's acceptance
    criterion. ERROR -- it blocks the export.

    **This is the rule that justifies P20's whole design.** Every other
    part of the phase -- the polymorphic owner, the batch model, the
    foreign key from a result to the test it answers -- exists so that this
    check can be arithmetic rather than reading. The limit is not a copy of
    the specification's limit; it IS the specification's limit, reached
    through `result.specification_test`. Tighten a limit in 3.2.S.4.1 and
    every batch already on file is re-judged against it, with nothing
    re-entered anywhere.

    The regulatory fact: an out-of-specification result in a batch analysis
    table is not a formatting problem. It is either a batch that should not
    have been released, or a specification the applicant does not actually
    meet, and either way the dossier as filed contradicts itself in a way
    an assessor will find -- because comparing those two tables is
    precisely what an assessor does with them.

    ERROR rather than WARNING, on the same test R20 passes and R19 fails:
    the platform is not guessing here. It holds the number, it holds the
    limit, and the comparison is decided. A rule that is certain about a
    fatal defect should gate; a rule that is inferring should not.

    Every finding names the batch, the test, the result and the limit --
    never just "inconsistent" -- because a finding a filer cannot act on
    without opening three screens is a finding they will not act on.
    """
    out: list[Finding] = []
    product = project.product

    for owner in [*product.apis, product]:
        section = "3.2.S.4.4" if owner is not product else "3.2.P.5.4"
        for batch in owner.batch_analyses:
            unchecked: list[str] = []
            for result in batch.results:
                test = result.specification_test
                if test is None:
                    # Structurally impossible through the API (the FK is
                    # NOT NULL and the router checks the owner match), so
                    # this can only be an in-memory object mid-construction.
                    # Skipping is right: there is no limit to judge against,
                    # and inventing one would be worse than saying nothing.
                    continue
                verdict = evaluate(test.acceptance_criterion, result.result)
                if verdict is None:
                    unchecked.append(test.test_name)
                    continue
                if verdict:
                    continue
                out.append(
                    Finding(
                        "R22",
                        Severity.ERROR,
                        "regulatory-limit",
                        f"Batch {batch.batch_number} of {_owner_label(owner)}: "
                        f"{test.test_name} result {result.result!r} is outside the "
                        f"acceptance criterion {test.acceptance_criterion!r} declared "
                        f"in the specification.",
                        section=section,
                    )
                )
            if unchecked:
                # ONE finding per batch rather than one per row, and INFO
                # rather than WARNING. A specification's first rows are
                # descriptive by nature ("White crystalline powder"), so a
                # per-row warning would fire several times on every batch of
                # every filing and teach the reader to scroll past the
                # report. What must never happen is silence: an unchecked
                # result is not a passed result, and the difference has to
                # be visible somewhere.
                out.append(
                    Finding(
                        "R22",
                        Severity.INFO,
                        "regulatory-limit",
                        f"Batch {batch.batch_number} of {_owner_label(owner)}: "
                        f"{len(unchecked)} result(s) could not be checked mechanically "
                        f"against their acceptance criteria ({', '.join(unchecked)}) -- "
                        f"these need a human read.",
                        section=section,
                    )
                )
    return out


# ---- P21: stability, as three independent checks ---------------------------
#
# The phase brief asks for three, and they stay three functions rather than
# one "stability check" for the reason the engine's registry exists: each
# is a separate regulatory statement, each fails for its own reason, and a
# filer reading the report has to be able to tell which one they tripped.
#
#   R05  the claim exceeds what the data supports   (upgraded above)
#   R23  a result inside the claim is out of specification
#   R24  the only data on file is accelerated
#
# They can fire together on one product, and when they do they are saying
# three different things -- not the same thing three times.


def _stability_claims(project):
    """Every claim stability has to support, as a `_StabilityClaim`.

    Two kinds of claim, and they are the same claim about different
    material. A finished product declares a SHELF LIFE, justified by
    3.2.P.8 data. A drug substance declares a RETEST PERIOD, justified by
    3.2.S.7 data -- the interval after which the material must be
    re-tested before use, not an expiry. Yielding both from one place is
    what lets R05, R23 and R24 each be written once instead of twice.
    """
    product = project.product
    yield _StabilityClaim(product, product.shelf_life_months, "Shelf life", "3.2.P.8")
    for api in product.apis:
        yield _StabilityClaim(api, api.retest_period_months, "Retest period", "3.2.S.7")


@dataclass(frozen=True)
class _StabilityClaim:
    """One shelf life or retest period, and where its evidence is filed.

    Carrying the 3.2.x.y STEM rather than a leaf number means each rule
    names the leaf it is actually talking about -- the data table for a
    contradicted result, the commitment leaf for missing data -- instead of
    slicing a section number apart at the call site.
    """

    owner: object
    months: int | None
    label: str
    stem: str

    @property
    def data_section(self) -> str:
        """3.2.S.7.3 / 3.2.P.8.3 -- where the timepoint table is filed."""
        return f"{self.stem}.3"

    @property
    def commitment_section(self) -> str:
        """3.2.S.7.2 / 3.2.P.8.2 -- the post-approval protocol and
        commitment, which is where an incomplete study is answered."""
        return f"{self.stem}.2"


@rule("R23")
def stability_results_within_specification(project) -> list[Finding]:
    """A stability result inside the claimed shelf life that does not meet
    its acceptance criterion. ERROR -- it blocks the export.

    **This is the rule P21 exists to make possible**, and it is R22's
    sibling: a stability result is judged against the limit reached through
    `result.specification_test`, never against a copy of it. Tighten a
    limit in 3.2.P.5.1 and every timepoint already on file is re-judged
    with nothing re-entered.

    The regulatory fact it encodes: a shelf life is a promise that the
    product still meets its specification at the end of it. An
    out-of-specification result at 6 months on a product claiming 24 is not
    a formatting problem -- it is the claim being contradicted by the
    applicant's own table, three sections later in the same dossier, and
    comparing those two things is precisely what an assessor does with
    3.2.P.8.3.

    Why "inside the claimed shelf life" and not "any failure at all": a
    study deliberately run past the claim is normal and good practice, and
    the point at which it eventually fails is *why* the claim is where it
    is. Flagging that as a defect would penalise the applicant who
    generated the most data. A failure beyond the claim still constrains
    R05 -- it caps `longest_passing_timepoint` -- so it is never ignored,
    only reported by the rule it actually bears on.

    Every finding names the timepoint, the test, the result and the limit,
    plus the batch and pack when they are on file. A finding a filer cannot
    act on without opening three screens is a finding they will not act on.
    """
    out: list[Finding] = []
    for claim in _stability_claims(project):
        for study in claim.owner.stability:
            unchecked: set[str] = set()
            for result in study.results:
                test = result.specification_test
                if test is None:
                    # Structurally impossible through the API (the FK is
                    # NOT NULL and the router checks the owner match), so
                    # this is an in-memory object mid-construction. There
                    # is no limit to judge against, and inventing one would
                    # be worse than saying nothing.
                    continue
                verdict = result.meets_criterion
                if verdict is None:
                    unchecked.add(test.test_name)
                    continue
                if verdict:
                    continue
                if claim.months is not None and result.timepoint_months > claim.months:
                    # Past the claim: the reason the claim stops there, not
                    # a defect. R05 already accounts for it.
                    continue
                out.append(
                    Finding(
                        "R23",
                        Severity.ERROR,
                        "regulatory-limit",
                        f"{_study_label(study, claim.owner)}: at "
                        f"{result.timepoint_months} months, {test.test_name} was "
                        f"{result.result!r} against the acceptance criterion "
                        f"{test.acceptance_criterion!r}. That is inside the claimed "
                        f"{claim.label.lower()}"
                        + (f" of {claim.months} months" if claim.months is not None else "")
                        + ".",
                        section=claim.data_section,
                    )
                )
            if unchecked:
                # ONE finding per study rather than one per cell, and INFO
                # rather than WARNING -- the same call R22 makes and for
                # the same reason. A specification's first rows are
                # descriptive by nature ("White crystalline powder"), so a
                # per-cell warning would fire dozens of times on every
                # filing and teach the reader to scroll past the report.
                # What must never happen is silence: an unchecked result is
                # not a passed result.
                out.append(
                    Finding(
                        "R23",
                        Severity.INFO,
                        "regulatory-limit",
                        f"{_study_label(study, claim.owner)}: {len(unchecked)} test(s) "
                        f"could not be checked mechanically against their acceptance "
                        f"criteria ({', '.join(sorted(unchecked))}) -- these need a "
                        f"human read.",
                        section=claim.data_section,
                    )
                )
    return out


@rule("R24")
def accelerated_data_alone_cannot_establish_shelf_life(project) -> list[Finding]:
    """A claim resting on accelerated data with no long-term study at all.
    WARNING.

    The regulatory fact: accelerated conditions (typically 40 C / 75 % RH
    for six months) exist to detect significant change and to support
    excursions and extrapolation -- not to establish the shelf life. ICH
    Q1A(R2) asks for long-term data on at least three primary batches, and
    ICH Q1E limits what may be extrapolated from a shorter long-term
    dataset. A dossier whose only stability evidence is accelerated has
    tested for a different question than the one the shelf life asks.

    WARNING rather than ERROR, and the two severities are doing different
    jobs. R05 has already blocked the export on the arithmetic -- there is
    no long-term support, so nothing covers the claim. This rule adds the
    *reason*, which is a judgement about study design rather than a
    comparison the platform can settle: an applicant may hold long-term
    data not yet entered, or may be filing with a commitment to complete
    it (which is what 3.2.P.8.2 is for). A rule that is inferring should
    surface, not gate; a rule that is certain should gate. This one is
    inferring.
    """
    out: list[Finding] = []
    for claim in _stability_claims(project):
        if claim.months is None:
            continue
        studies = list(claim.owner.stability)
        if not studies:
            # Nothing on file at all is R05's finding, not this one. Saying
            # "your data is accelerated-only" about no data would be a
            # finding about a study that does not exist.
            continue
        if any(study.study_type is StabilityStudyType.LONG_TERM for study in studies):
            continue
        accelerated, _ = supported_months(
            [s for s in studies if s.study_type is StabilityStudyType.ACCELERATED]
        )
        out.append(
            Finding(
                "R24",
                Severity.WARNING,
                "consistency",
                f"{claim.label} of {_owner_label(claim.owner)} is {claim.months} months, "
                f"supported only by accelerated data ({accelerated} months). Accelerated "
                f"conditions detect significant change and support extrapolation; they do "
                f"not establish a shelf life on their own (ICH Q1A(R2)). File long-term "
                f"data, or a post-approval stability commitment in "
                f"{claim.commitment_section}.",
                section=claim.data_section,
            )
        )
    return out


def _study_label(study, owner) -> str:
    """How one study is named in a finding: the material, the condition,
    and -- when they are on file -- the batch and the pack.

    The batch and pack are what make a finding actionable. "Amoxicillin
    30C/65%RH" identifies a study; "batch EX/24/0117, blister" identifies
    the page of the stability report the filer has to open.
    """
    parts = [f"{_owner_label(owner)} {study.condition}"]
    if study.batch_analysis is not None:
        parts.append(f"batch {study.batch_analysis.batch_number}")
    if study.packaging is not None:
        parts.append(study.packaging.description)
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# P22 -- the rules a structured bioequivalence study makes possible.
#
# All three read numbers that did not exist before this phase. Until the
# study was `kind` + `reference_product` + a paragraph, the only checkable
# fact about the single most important document in a multisource dossier
# was that a row existed.
# ---------------------------------------------------------------------------


@rule("R25")
def confidence_interval_within_acceptance_window(project) -> list[Finding]:
    """A 90 % confidence interval outside the acceptance window. ERROR --
    it blocks the export.

    **This is the rule the phase exists for.** For a multisource filing,
    whether the 90 % CI of the test/reference ratio of Cmax and AUC lies
    inside the window IS the approval decision -- everything else in the
    dossier establishes that the product is made consistently, and this
    establishes that it works. A dossier that ships with a failing interval
    is not a dossier with a defect in it; it is an application that has
    answered its own central question in the negative.

    ## What the finding has to say

    The PARAMETER and the BOUND, both. "The study failed" sends a filer
    back to a hundred-page report. "AUC(0-t): the lower bound is 76.40 %,
    outside 80.00 - 125.00 %" is a line they can act on -- and the two
    bounds mean different things, since a low lower bound is a product
    that under-delivers and a high upper bound is one that over-delivers.

    ## Why the window is not in this function

    It is a regulatory parameter, and it is in the region profile beside
    the Module 1 slots and the applicability table (see
    `BioequivalenceWindow`). Three consequences that matter: an agency
    republishing its table is an edit to config, not to a rule; a narrow-
    therapeutic-index product is judged against 90.00 - 111.11 % with no
    branch here at all; and the window this rule checks is the same object
    the BTI form PRINTS, so a form cannot state a criterion the gate does
    not apply.
    """
    profile = REGION_PROFILES.get(project.region)
    if profile is None:
        # An unmodelled region declares no criteria. Same call
        # `resolve_applicability` makes: nothing declared, nothing claimed
        # -- and an export must not be blocked by a window nobody set.
        return []

    window = profile.window_for(project.product)
    out: list[Finding] = []

    for study in project.product.bioequivalence_studies:
        for result in study.results:
            for bound in result.outside(window.lower, window.upper):
                value = result.ci_lower if bound == "lower" else result.ci_upper
                out.append(
                    Finding(
                        "R25",
                        Severity.ERROR,
                        "consistency",
                        f"Study {study.study_identifier}: the 90 % confidence interval for "
                        f"{result.parameter.value} has a {bound} bound of {value:.2f} %, "
                        f"outside the acceptance window {window.label}. Bioequivalence is "
                        f"not demonstrated.",
                        section="5.3.1.2",
                    )
                )
    return out


@rule("R26")
def study_comparator_matches_the_declared_reference_product(project) -> list[Finding]:
    """The comparator the study dosed must be the one the application names.

    **This is the cross-module check the platform was built for.** The
    reference product is named in Module 1 (the registration form, 1.2), in
    Module 2 (the quality overall summary, 2.3) and in Module 5 (the study
    report itself). In a hand-assembled dossier those are three separate
    typings of one fact, done weeks apart by different people, and the
    failure is entirely ordinary: the comparator originally planned is not
    the one the CRO could source, the study is run against what was
    bought, and Module 1 still names the original.

    An assessor catches it by reading three modules against each other. It
    is caught here by comparing two fields.

    ## Why the two are stored separately at all

    `Product.reference_product_name` is the CLAIM the application makes;
    the study's `ReferenceProduct` row is what was actually DOSED. Storing
    one field and rendering it everywhere would make this rule a check
    that a value equals itself -- and would make the real error
    unrepresentable in the model while leaving it perfectly possible in
    the paperwork. It is the same claim-against-evidence shape R05 uses
    for the shelf life.

    ## Why the comparison is loose

    Names are typed by humans and case, spacing and punctuation vary
    ("Amoxil 500mg Capsules" and "Amoxil 500 mg capsules" are the same
    product). Matching those as different would fire on every filing and
    teach the filer to ignore the rule -- the failure mode a check must
    never have. What it will not forgive is a different BRAND: "Amoxil"
    against "Ospamox" is two products, and no normalisation makes them one.
    """
    product = project.product
    declared = product.reference_product_name
    out: list[Finding] = []

    for study in product.bioequivalence_studies:
        reference = study.reference_product
        if reference is None:
            out.append(
                Finding(
                    "R26",
                    Severity.ERROR,
                    "completeness",
                    f"Study {study.study_identifier} names no reference product. A "
                    f"comparative bioequivalence study without an identified comparator "
                    f"cannot be assessed (1.4.1 and 5.2 have nothing to print).",
                    section="5.3.1.2",
                )
            )
            continue

        if not declared:
            # WHY a WARNING here and an ERROR below: the study HAS a
            # comparator, and the application simply has not restated it.
            # Nothing in the dossier contradicts anything; a field is
            # empty. The rendered 1.2 will show the marker, and blocking
            # an export over a field the study can fill would be a gate
            # with no defect behind it.
            out.append(
                Finding(
                    "R26",
                    Severity.WARNING,
                    "completeness",
                    f"Study {study.study_identifier} was run against {reference.identity}, "
                    f"but the application declares no reference product, so 1.2.2 and "
                    f"2.3 have nothing to name.",
                    # P24d: renumbered with the section itself. A finding
                    # that points at a leaf number the package does not
                    # contain sends the filer to a section that is not
                    # there.
                    section="1.2.2",
                )
            )
            continue

        if _normalise_product_name(reference.name) != _normalise_product_name(declared):
            out.append(
                Finding(
                    "R26",
                    Severity.ERROR,
                    "consistency",
                    f"Study {study.study_identifier} was run against "
                    f"{reference.identity!r}, but the application declares its reference "
                    f"product as {declared!r} (printed at 1.2 and 2.3). The dossier gives "
                    f"two different comparators for one product.",
                    section="5.3.1.2",
                )
            )
            continue

        declared_maker = product.reference_product_manufacturer
        if (
            declared_maker
            and reference.manufacturer
            and _normalise_product_name(reference.manufacturer)
            != _normalise_product_name(declared_maker)
        ):
            out.append(
                Finding(
                    "R26",
                    Severity.ERROR,
                    "consistency",
                    f"Study {study.study_identifier} used {reference.name} made by "
                    f"{reference.manufacturer!r}, but the application declares the "
                    f"reference product's manufacturer as {declared_maker!r}. A generic "
                    f"is equivalent to a specific innovator product, not to a name.",
                    section="5.3.1.2",
                )
            )
    return out


def _normalise_product_name(name: str) -> str:
    """Case, spacing and punctuation folded away entirely; the characters
    that carry meaning kept.

    Spacing is REMOVED rather than merely collapsed, and that is the
    difference between a rule that works and one everybody switches off:
    "Amoxil 500mg Capsules" and "Amoxil 500 mg capsules" are the same
    product, typed by two people, and a rule that reported them as two
    comparators would fire on every filing.

    It deliberately does NOT strip strengths or dosage forms: "amoxil250mg"
    and "amoxil500mg" stay different, so a study run against the wrong
    strength of the right brand is still caught. And no amount of folding
    turns Amoxil into Ospamox, which is the case that matters.
    """
    return re.sub(r"[^a-z0-9]+", "", name.lower())


@rule("R27")
def test_batch_is_representative_of_commercial_scale(project) -> list[Finding]:
    """The bioequivalence batch must be a defensible fraction of production.

    The regulatory fact (WHO TRS 992 Annex 7, and the same position at EMA
    and FDA): the batch used in the bioequivalence study should be at least
    one tenth of the proposed commercial batch, or 100 000 units, whichever
    is greater. The reasoning is not arbitrary -- a study run on a
    laboratory-scale batch demonstrates that the laboratory-scale batch is
    bioequivalent, and says nothing about the material a patient will
    actually be dispensed. Scale-up changes dissolution.

    ## Why this is cross-module and why that is the point

    The test batch size is in Module 5. The proposed commercial batch size
    is in Module 3 -- leaf 3.2.P.3.2, the batch formula, where it has been
    modelled since P01 as `BatchFormulaLine.batch_size_units`. Nobody
    reading either module alone can see the problem; an assessor holding
    both open can, and does. This is a genuine regulatory finding that
    exists only in the space BETWEEN two modules, which is the class of
    defect a single-source-of-truth platform is uniquely able to catch.

    ## Why the thresholds are config

    Two numbers stated in guidance, re-confirmable by reading one file --
    the same reasoning as R25's window. See
    `app.ctd.region_profiles.TestBatchRule`.

    Silent when either figure is absent: a study whose batch size has not
    been entered is a data-entry gap, not a scale defect, and a rule that
    guessed here would block filings over an empty field.
    """
    try:
        profile = get_region_profile(project.region)
    except KeyError:
        return []

    product = project.product
    commercial = _commercial_batch_size(product)
    if commercial is None:
        return []

    rule_ = profile.test_batch_rule
    required = rule_.required_units(commercial)
    out: list[Finding] = []

    for study in product.bioequivalence_studies:
        size = study.test_batch_size_units
        if size is None or size >= required:
            continue
        out.append(
            Finding(
                "R27",
                Severity.ERROR,
                "consistency",
                f"Study {study.study_identifier} was run on a test batch of {size:,} "
                f"units, but the commercial batch declared in 3.2.P.3.2 is "
                f"{commercial:,} units. The biobatch must be at least "
                f"{rule_.minimum_fraction:%} of the commercial batch or "
                f"{rule_.minimum_units:,} units, whichever is greater -- "
                f"{required:,} units here.",
                section="5.3.1.2",
            )
        )
    return out


def _commercial_batch_size(product) -> int | None:
    """The proposed commercial batch size, from the batch formula (3.2.P.3.2).

    Takes the MAXIMUM across the formula's lines. Every line of one batch
    formula should declare the same batch size, and rule R04's arithmetic
    is where a disagreement between them belongs -- taking the largest here
    means this rule states the most demanding threshold the dossier's own
    numbers imply, rather than picking whichever line happened to sort
    first.
    """
    sizes = [
        line.batch_size_units for line in product.batch_formula if line.batch_size_units is not None
    ]
    return max(sizes) if sizes else None


# =============================================================================
# P23 -- the product information rules
# =============================================================================
#
# Read these six against app/templating/product_information.py, because what
# they check and what they DO NOT check is the phase's whole argument.
#
# The three documents cannot disagree with EACH OTHER: they render from one
# `shared_values` call, so there is one expression of the shelf life and
# nothing to contradict it. R31 asserts that anyway, as a tripwire.
#
# What CAN still be wrong is the relationship between the product
# information and the rest of the dossier -- the excipient list against the
# batch formula, the storage statement against the temperature the study
# actually ran at, the leaflet's prose against the SmPC's own lists. Those
# are what R28, R29, R32 and R33 check, and every one of them is a real
# deficiency letter.


@rule("R28")
def leaflet_excipients_match_the_batch_formula(project) -> list[Finding]:
    """Every excipient the leaflet and SmPC 6.1 list must appear in the
    batch formula, and every non-active batch formula line must appear as
    an excipient. ERROR -- it blocks the export.

    ## Why this is the check, and not a check on the leaflet's text

    SmPC 6.1 and the leaflet's "other ingredients" both render from
    `product.excipients` (app/templating/product_information.py), so a
    leaflet cannot list an excipient the SmPC does not. That half is
    structural.

    What is NOT structural is the relationship to 3.2.P.3.2. The batch
    formula is the MANUFACTURING truth -- what is actually weighed -- and
    the excipient rows are the QUALITY truth that 3.2.P.4.1 is built from.
    They are separate tables, entered at different times, and they drift:
    a formulation change adds a glidant to the batch formula and nobody
    updates the leaflet, or an excipient is removed from the formula and
    stays in the leaflet forever.

    A patient with a lactose intolerance reads the leaflet. That is why
    this is an ERROR and not a warning: an undeclared excipient in a
    patient-facing document is a safety issue, not a bookkeeping one.

    ## Why the comparison is on normalised names

    The two tables are typed by different people at different times, so
    "Magnesium Stearate" and "magnesium stearate" are the same material and
    must not be reported as a divergence. Anything beyond case and spacing
    -- "Mg stearate" -- IS reported, because at that point the platform
    genuinely cannot tell whether it is the same material, and guessing
    would be the one behaviour that makes the rule untrustworthy.
    """
    product = project.product
    declared = {_normalise_component(e.name): e.name for e in product.excipients}
    in_formula = {
        _normalise_component(line.component): line.component
        for line in product.batch_formula
        if not line.is_active
    }
    if not declared and not in_formula:
        # Neither table has been filled in yet. That is completeness
        # territory (R30 for the product information, R07-style rules for
        # the formula), not a divergence -- and reporting "these two empty
        # lists disagree" would be noise on every new project.
        return []

    out: list[Finding] = []
    for key, name in sorted(declared.items()):
        if key not in in_formula:
            out.append(
                Finding(
                    "R28",
                    Severity.ERROR,
                    "consistency",
                    f"Excipient '{name}' is listed in the product information "
                    f"(SmPC 6.1 and the patient leaflet, 1.3.1/1.3.3) but has no line "
                    f"in the batch formula (3.2.P.3.2). Either it is not in the "
                    f"product, or the batch formula is incomplete.",
                    section="1.3.3",
                )
            )
    for key, component in sorted(in_formula.items()):
        if key not in declared:
            out.append(
                Finding(
                    "R28",
                    Severity.ERROR,
                    "consistency",
                    f"Batch formula line '{component}' (3.2.P.3.2) is not declared as "
                    f"an excipient, so it appears in neither SmPC 6.1 nor the patient "
                    f"leaflet (1.3.1/1.3.3). A patient reading the leaflet would not "
                    f"know this ingredient is in the product.",
                    section="1.3.3",
                )
            )
    return out


def _normalise_component(name: str) -> str:
    """Case- and spacing-insensitive key for a material name. Nothing more
    aggressive on purpose -- see R28's docstring."""
    return " ".join((name or "").lower().split())


# Temperatures a storage statement is written in, in the two forms a real
# label uses: an upper bound ("Store below 30 C") and a range ("Store at 2 C
# to 8 C"). Both are matched, and the HIGHEST number found is the one that
# matters -- it is the warmest condition the label permits, and therefore
# the one the stability data has to have covered.
_STORAGE_TEMPERATURE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:°\s*)?C\b", re.IGNORECASE)


def _max_temperature(text: str | None) -> float | None:
    if not text:
        return None
    matches = _STORAGE_TEMPERATURE_RE.findall(text)
    return max(float(match) for match in matches) if matches else None


@rule("R29")
def storage_statement_supported_by_stability_conditions(project) -> list[Finding]:
    """The storage temperature the label permits must be one the long-term
    stability study actually ran at. ERROR -- it blocks the export.

    ## The defect, in one sentence

    A label that says "Store below 30 C" over a study run at 25 C is
    claiming twelve months of evidence the applicant does not have.

    ## Why this is a real and common failure, not a contrivance

    The long-term condition is chosen by CLIMATIC ZONE. Zone II (most of
    Europe) tests at 25 C / 60 % RH; Zone IVb (Nigeria, and most of
    tropical Asia) tests at 30 C / 75 % RH. A dossier assembled from a
    European parent filing arrives with 25 C data and a label that was
    rewritten for the Nigerian market -- and the two now disagree by five
    degrees that nobody typed deliberately. NAFDAC asks for Zone IVb data
    precisely because that gap is the norm.

    ## Why it reads temperatures out of strings rather than asking for a field

    Both sides are free text today: `Product.storage_condition` is what
    goes on the label, and `StabilityStudy.condition` is what the protocol
    was written as ("30 C / 75 % RH"). Parsing is honest about that -- it
    is silent when it cannot find a temperature on either side, so a
    storage statement with no number in it ("Protect from light") produces
    no finding rather than a false one. The day both become structured
    fields, this rule reads them directly and the regex goes.

    The comparison is on the WARMEST number on each side, because that is
    what the claim actually is: the label permits storage up to some
    temperature, and the study demonstrates stability up to some
    temperature.
    """
    product = project.product
    permitted = _max_temperature(product.storage_condition)
    if permitted is None:
        return []

    long_term = [
        study for study in product.stability if study.study_type is StabilityStudyType.LONG_TERM
    ]
    tested = [(study, _max_temperature(study.condition)) for study in long_term]
    tested = [(study, temperature) for study, temperature in tested if temperature is not None]
    if not tested:
        return []

    warmest_study, warmest = max(tested, key=lambda pair: pair[1])
    if permitted <= warmest:
        return []
    return [
        Finding(
            "R29",
            Severity.ERROR,
            "consistency",
            f"The storage statement printed on the label, the SmPC (6.4) and the "
            f"patient leaflet -- '{product.storage_condition}' -- permits storage up "
            f"to {permitted:g} C, but the warmest long-term stability study on file "
            f"ran at {warmest:g} C ('{warmest_study.condition}', 3.2.P.8.3). The data "
            f"does not support the storage condition being claimed.",
            section="1.3.2",
        )
    ]


# The SmPC sections a dossier cannot be filed without, and the ones it
# should not be. The split is regulatory, not stylistic: 4.1, 4.2 and 4.3
# ARE the marketing authorisation -- what the medicine is for, how much of
# it to take, and who must not take it. An application missing any of the
# three has not stated what it is applying for.
# Each entry is (attribute on ProductInformation, the heading a filer sees).
# The attribute names for the three list sections are the model's coercing
# PROPERTIES (`contraindication_terms`, not `contraindications`), so a row
# holding null instead of [] reads as empty rather than raising here.
_MANDATORY_SMPC_SECTIONS: tuple[tuple[str, str], ...] = (
    ("therapeutic_indications", "4.1 Therapeutic indications"),
    ("posology_and_administration", "4.2 Posology and method of administration"),
    ("contraindication_terms", "4.3 Contraindications"),
)
_EXPECTED_SMPC_SECTIONS: tuple[tuple[str, str], ...] = (
    ("warning_terms", "4.4 Special warnings and precautions for use"),
    ("interactions", "4.5 Interaction with other medicinal products"),
    ("pregnancy_and_lactation", "4.6 Fertility, pregnancy and lactation"),
    ("effects_on_driving", "4.7 Effects on ability to drive and use machines"),
    ("adverse_effects", "4.8 Undesirable effects"),
    ("overdose", "4.9 Overdose"),
    ("incompatibilities", "6.2 Incompatibilities"),
    ("special_precautions_for_disposal", "6.6 Special precautions for disposal"),
)


@rule("R30")
def product_information_sections_are_present(project) -> list[Finding]:
    """The SmPC's authored sections must actually be authored. ERROR for
    the three that constitute the authorisation, WARNING for the rest.

    ## Why a completeness rule earns its place here

    Everything else about the product information is DERIVED, so it cannot
    be missing while the underlying data exists -- a shelf life is either
    on the product or the whole dossier knows it is not. The clinical
    particulars are the opposite: they live nowhere else, so an empty 4.3
    produces a perfectly well-formed SmPC with no contraindications
    section, which is a document that looks finished and is not. That is
    the failure this platform exists to catch, arriving from the one
    direction derivation cannot cover.

    ## Why two severities

    4.1, 4.2 and 4.3 are the application. Without them there is nothing to
    approve, so they block. The rest genuinely can be legitimately short --
    a product with no known interactions has an honest 4.5 -- but they
    cannot be SILENT, because "no interactions are known" and "nobody
    filled this in" are different statements and only one of them is a
    filing. So they warn, and the filer decides.
    """
    information = project.product.product_information
    if information is None:
        return [
            Finding(
                "R30",
                Severity.ERROR,
                "completeness",
                "No product information has been entered, so the SmPC (1.3.1), the "
                "labels (1.3.2) and the patient leaflet (1.3.3) have no clinical "
                "particulars -- no indications, no posology and no contraindications.",
                section="1.3.1",
            )
        ]

    out: list[Finding] = []
    for attribute, heading, severity in (
        *((*entry, Severity.ERROR) for entry in _MANDATORY_SMPC_SECTIONS),
        *((*entry, Severity.WARNING) for entry in _EXPECTED_SMPC_SECTIONS),
    ):
        value = getattr(information, attribute)
        if value:
            continue
        out.append(
            Finding(
                "R30",
                severity,
                "completeness",
                f"SmPC section {heading} is empty. It is authored content -- it "
                f"exists nowhere else in the dossier to be derived from -- and it is "
                f"printed in the SmPC (1.3.1) and, for the patient-facing sections, "
                f"the leaflet (1.3.3).",
                section="1.3.1",
            )
        )
    return out


# The three documents, and the section number each divergence should be
# reported against. Ordered so a finding names them the way a filer reads
# them: the SmPC is the source document, the other two follow from it.
_PRODUCT_INFORMATION_LEAVES = ("1.3.1", "1.3.2", "1.3.3")


@rule("R31")
def product_information_agrees_across_the_three_documents(project) -> list[Finding]:
    """Strength, shelf life, storage and pack size must read identically in
    the SmPC, the label and the leaflet. ERROR -- it blocks the export.

    ## This rule cannot fire today, and that is the point

    All three documents render from one `shared_values` call
    (app/templating/product_information.py), so there is one expression of
    each of these facts and nothing for it to disagree with. This rule asks
    the three FINISHED CONTEXTS anyway -- what each document will actually
    print -- rather than asking the shared function, which would be a check
    that a value equals itself.

    It is a regression tripwire, and the regression it is waiting for is
    specific and likely: someone adds a `shelf_life_months` column to
    ProductInformation because the label "needs its own", or a context
    builder starts formatting a value locally instead of reading `shared`.
    Either would restore the exact defect this phase removed, and it would
    restore it silently -- three documents that look right individually and
    disagree in a pile on an assessor's desk.

    A test (`test_none_of_the_three_can_be_made_to_disagree`) holds the same
    line by forcing a divergence and asserting this fires. The rule is what
    holds it in a running system, on real data, after the test has been
    forgotten.

    ## Why it is an ERROR when it cannot fire

    Severity describes what the finding MEANS, not how likely it is. If
    these three ever disagree, the package must not ship.
    """
    contexts = {}
    for number in _PRODUCT_INFORMATION_LEAVES:
        contexts[number] = build_context(number, project).get("shared", {})

    fields = sorted({field for shared in contexts.values() for field in shared})
    reference_number = _PRODUCT_INFORMATION_LEAVES[0]

    out: list[Finding] = []
    for field in fields:
        reference = contexts[reference_number].get(field)
        for number in _PRODUCT_INFORMATION_LEAVES[1:]:
            other = contexts[number].get(field)
            if other == reference:
                continue
            out.append(
                Finding(
                    "R31",
                    Severity.ERROR,
                    "consistency",
                    f"'{field}' does not agree across the product information: "
                    f"{reference_number} states {reference!r} and {number} states "
                    f"{other!r}. These three documents are rendered from one dataset "
                    f"precisely so this cannot happen; a divergence means a second "
                    f"copy of the value has been introduced.",
                    section=number,
                )
            )
    return out


@rule("R32")
def leaflet_prose_carries_every_contraindication(project) -> list[Finding]:
    """Every contraindication the SmPC states should be recognisable in the
    leaflet's own words. WARNING.

    ## What is structural and what is not

    The leaflet PRINTS the contraindication list verbatim -- it renders the
    same `contraindications` entries the SmPC does, so it cannot omit one.
    That guarantee is in the template, not in this rule.

    What this rule checks is the drafted prose that sits above the list: the
    "before you take it" section, which is what a patient actually reads.
    Prose is where a contraindication goes missing, and it goes missing by
    paraphrase -- the list says "severe hepatic impairment" and the prose
    talks about kidneys.

    ## Why a WARNING and not an ERROR

    The check is keyword-based, and a good leaflet paraphrases: "severe
    hepatic impairment" correctly becomes "serious liver problems", which
    shares no whole word with the source. So a miss here means "a human
    should look", not "this is wrong" -- and a rule that blocked exports on
    good plain-language writing would teach filers to write badly. The
    finding names the contraindication so the reviewer knows where to look.

    R33 is where the leaflet's register is checked; this is where its
    COMPLETENESS is.
    """
    product = project.product
    information = product.product_information
    if information is None:
        return []
    terms = information.contraindication_terms
    if not terms:
        return []

    prose = _leaflet_prose(project)
    if prose is None:
        # Nothing has been drafted and approved yet, so there is no prose
        # to have lost anything. R20 is what complains about a leaf still
        # holding an unfilled placeholder at export.
        return []

    lowered = prose.lower()
    out: list[Finding] = []
    for term in terms:
        if _shares_a_content_word(term, lowered):
            continue
        out.append(
            Finding(
                "R32",
                Severity.WARNING,
                "consistency",
                f"The patient leaflet's drafted text does not appear to mention the "
                f"contraindication '{term}' that the SmPC states at 4.3. It is still "
                f"printed in the leaflet's own list, so it is not missing from the "
                f"document -- but the prose a patient actually reads may not carry it.",
                section="1.3.3",
            )
        )
    return out


# Words that carry no clinical content, so sharing one is not evidence that
# a contraindication was carried over.
#
# Two kinds are listed, and the second kind is the one that took a failing
# test to find. Ordinary grammar words are obvious. The other kind is the
# vocabulary EVERY leaflet is made of -- "medicine", "take", "doctor",
# "problem" -- and without them the check passes on any prose at all: the
# contraindication "jaundice or a liver problem after taking this medicine"
# was satisfied by a sentence that said only "do not take this medicine if
# you are allergic to penicillins", because both contain "medicine".
#
# What is left after both lists is the clinically DISTINCTIVE word -- the
# organ, the condition, the drug class -- which is the word a paraphrase
# has to keep in order to still be saying the same thing.
_STOPWORDS = frozenset(
    {
        # grammar
        "a",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "had",
        "has",
        "have",
        "if",
        "in",
        "is",
        "it",
        "not",
        "of",
        "on",
        "or",
        "other",
        "the",
        "this",
        "to",
        "with",
        "who",
        # the vocabulary every leaflet is written in
        "after",
        "before",
        "been",
        "condition",
        "doctor",
        "ever",
        "known",
        "medicine",
        "medicines",
        "patients",
        "problem",
        "problems",
        "severe",
        "take",
        "taken",
        "taking",
        "tell",
        "use",
        "used",
        "using",
        "you",
        "your",
    }
)


def _shares_a_content_word(term: str, prose_lower: str) -> bool:
    """True if any clinically meaningful word of `term` appears in `prose`.

    Deliberately generous -- one shared content word is enough. The rule it
    backs is a WARNING whose job is to point a reviewer at a paraphrase
    that may have gone too far, and a stricter test would fire on every
    well-written leaflet.
    """
    words = [word for word in re.findall(r"[a-z]{3,}", term.lower()) if word not in _STOPWORDS]
    if not words:
        return True
    return any(re.search(rf"\b{re.escape(word)}", prose_lower) for word in words)


def _leaflet_prose(project) -> str | None:
    """What leaf 1.3.3 actually says, or None if nothing has been stored yet.

    Reads `Section.narrative_text` -- the same already-loaded collection
    R01-R03 scan, and the seam P06 built for exactly this: the rule engine
    is synchronous, so it cannot query `NarrativeGeneration` for approved
    slot text, and `Section` is where a project's rendered prose is put for
    rules to read. A leaflet whose narrative has not been generated,
    approved and stored simply has no prose here, and both rules that call
    this stay silent rather than complaining about text nobody has written.
    """
    texts = [
        section.narrative_text
        for section in project.sections
        if section.number == "1.3.3" and section.narrative_text
    ]
    return "\n".join(texts) if texts else None


@rule("R33")
def leaflet_reads_as_plain_language(project) -> list[Finding]:
    """Approved patient leaflet text must meet the plain-language register.
    WARNING.

    The same check `app.narrative.guardrails.check_patient_register` runs on
    a fresh draft, run again here on text a human has APPROVED -- which is
    the only place it can act as a gate. A guardrail warning at generation
    time is advice; the same finding at export time is on the readiness
    report the filer has to look at before building the package.

    WARNING rather than ERROR, deliberately. Jargon in a leaflet is a
    readability failure, not a false statement -- unlike an unsupported
    shelf life, it does not make the dossier wrong, it makes it hard to
    read. Blocking on it would also put the platform in the position of
    refusing to export a filing over a word choice a competent regulatory
    writer may have made on purpose. The finding names the term and the
    plain alternative, which is what actually gets it fixed.
    """
    text = _leaflet_prose(project)
    if text is None:
        return []
    return [
        Finding(
            "R33",
            Severity.WARNING,
            "narrative",
            f"Patient leaflet (1.3.3): {warning}",
            section="1.3.3",
        )
        for warning in check_patient_register(text)
    ]
