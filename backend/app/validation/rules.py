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
from datetime import date

from app.validation.engine import Finding, Severity, rule
from app.models import (
    CertificateType,
    DeclarationType,
    DECLARATIONS_REQUIRING_NOTARIZATION,
    DosageForm,
    GMPStatus,
    ManufacturerRole,
    PackagingComponent,
    Region,
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
    """Declared shelf life must be supported by long-term stability duration.
    A product with no declared shelf life yet has nothing for this rule to
    check -- that's R06/R07-style completeness territory, not this rule's
    job, so it stays silent rather than crashing on None."""
    product = project.product
    if product.shelf_life_months is None:
        return []
    supported = max((s.duration_months for s in product.stability), default=0)
    if product.shelf_life_months > supported:
        return [
            Finding(
                "R05",
                Severity.ERROR,
                "consistency",
                f"Shelf life {product.shelf_life_months} months exceeds the "
                f"{supported} months supported by long-term stability data.",
            )
        ]
    return []


@rule("R06")
def generic_requires_bioequivalence(project) -> list[Finding]:
    """A generic/renewal must include bioequivalence evidence (Module 5.3.1)."""
    product = project.product
    has_be = any(c.kind == "bioequivalence" for c in product.clinical)
    if not has_be:
        return [
            Finding(
                "R06",
                Severity.ERROR,
                "completeness",
                "No bioequivalence study found, but one is required for this "
                "generic product (Module 5.3.1).",
            )
        ]
    return []


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
                    f"{api.inn_name} has no specification on file "
                    f"(required, Module 3.2.S.4.1).",
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
                    f"Manufacturer {manufacturer.name}'s GMP status is "
                    f"'{status}', not certified.",
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
    return out


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
    relevant = [p for p in product.packaging if p.component in _PACKAGING_LABEL_COMPONENTS]
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


@rule("R13", regions=[Region.NAFDAC])
def nafdac_cpp_certificate_required(project) -> list[Finding]:
    """A NAFDAC filing requires a Certificate of Pharmaceutical Product
    (CPP) that is actually on file and unexpired -- region-scoped, so
    this never runs at all for an FDA/EU project (see run_all's
    filtering in engine.py), unlike R01-R12 which apply everywhere."""
    product = project.product
    cpps = [c for c in product.certificates if c.certificate_type == CertificateType.CPP]
    if not cpps:
        return [
            Finding(
                "R13",
                Severity.ERROR,
                "completeness",
                "No Certificate of Pharmaceutical Product (CPP) on file -- "
                "required for a NAFDAC filing.",
            )
        ]
    if not any(c.expiry_date is not None and c.expiry_date >= date.today() for c in cpps):
        return [
            Finding(
                "R13",
                Severity.ERROR,
                "completeness",
                "The Certificate of Pharmaceutical Product (CPP) on file is "
                "expired or has no expiry date recorded.",
            )
        ]
    return []


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


_NAFDAC_REQUIRED_DECLARATIONS = (
    DeclarationType.POWER_OF_ATTORNEY,
    DeclarationType.DECLARATION_OF_AUTHENTICITY,
)


@rule("R16", regions=[Region.NAFDAC])
def nafdac_required_declarations_present(project) -> list[Finding]:
    """A NAFDAC filing specifically requires a Power of Attorney and a
    Declaration of Authenticity to be on file at all -- distinct from R15,
    which only checks that whatever declarations ARE attached are signed.
    A project with zero declarations passes R15 vacuously but must fail
    here."""
    present = {d.declaration_type for d in project.declarations}
    missing = [t for t in _NAFDAC_REQUIRED_DECLARATIONS if t not in present]
    if missing:
        names = ", ".join(t.value for t in missing)
        return [
            Finding(
                "R16",
                Severity.ERROR,
                "completeness",
                f"Missing required declaration(s) for a NAFDAC filing: {names}.",
            )
        ]
    return []
