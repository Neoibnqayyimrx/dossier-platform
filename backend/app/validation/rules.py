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

from app.validation.engine import Finding, Severity, rule
from app.models import DosageForm

# Words that denote a dosage form, mapped to the enum member they imply.
_FORM_WORDS = {
    "tablet": DosageForm.TABLET,
    "tablets": DosageForm.TABLET,
    "capsule": DosageForm.CAPSULE_HARD,
    "capsules": DosageForm.CAPSULE_HARD,
    "syrup": DosageForm.SYRUP,
    "injection": DosageForm.INJECTION,
}


@rule("R01")
def strength_consistency(project) -> list[Finding]:
    """Every strength stated near the active in narrative must equal the
    product's declared strength. Catches LAMOX's '250mg' vs 500mg typo."""
    product = project.product
    declared = float(product.strength_value)
    generic = product.generic_name.lower()
    out: list[Finding] = []
    for sec in project.sections:
        text = sec.narrative_text
        # find "<generic> ... <n> mg" mentions, tolerating words in between
        for m in re.finditer(
            rf"{re.escape(generic)}[^.\n]{{0,40}}?(\d{{2,5}})\s*mg",
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
                        f"Section {sec.number} states {product.generic_name} "
                        f"{value:.0f} mg, but the product strength is {declared:.0f} mg.",
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
    """Reconcile the active's declared batch quantity against
    strength x salt_factor x batch_size. Demonstrates a rule that PASSES on
    LAMOX (144 kg trihydrate is correct for 500 mg base x 250,000)."""
    product = project.product
    if not product.apis:
        return []
    api = product.apis[0]
    salt_factor = float(api.salt_factor)
    out: list[Finding] = []
    for line in product.batch_formula:
        if not line.is_active or line.declared_batch_qty_kg is None:
            continue
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
    """Declared shelf life must be supported by long-term stability duration."""
    product = project.product
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
