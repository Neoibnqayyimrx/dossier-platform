"""A plausible BP-style drug-substance specification, shared by the seeds.

WHY the seeds share one builder: EXAMOX, LAMOX and AMPICLOX all used the
same free-text string before this ("Assay 90.0-120.0%, related substances
per BP monograph"), and three hand-written copies of the same table would
drift. The shape is what the fixtures are demonstrating; the numbers are
illustrative.

Every `method` here is a CITATION, never method text. Pharmacopoeial
monographs are copyrighted (AGENTS.md §5): a dossier references "BP
monograph", it does not reproduce it, and the knowledge base never
ingests it.

These values are realistic but invented -- do not treat them as the actual
BP limits for any substance.
"""

from __future__ import annotations

from app.models import SpecificationTest


def bp_substance_specification(assay_lower: str = "98.0", assay_upper: str = "102.0"):
    """The conventional row order an assessor expects: identity first
    (is it the right substance?), then assay (how much?), then impurities
    and physical attributes."""
    rows = [
        ("Description", "Visual", "White to off-white crystalline powder"),
        ("Identification A", "IR absorption, BP monograph", "Complies with reference spectrum"),
        ("Identification B", "HPLC retention time, BP monograph", "Corresponds to reference"),
        ("Assay (anhydrous basis)", "HPLC, BP monograph", f"{assay_lower} - {assay_upper} % w/w"),
        ("Related substances - any individual", "HPLC, BP monograph", "NMT 1.0 %"),
        ("Related substances - total", "HPLC, BP monograph", "NMT 3.0 %"),
        ("Water content", "Karl Fischer, BP monograph", "NMT 14.5 %"),
        ("Sulphated ash", "BP monograph", "NMT 1.0 %"),
        ("Residual solvents", "GC, ICH Q3C", "Complies with ICH Q3C limits"),
        ("Heavy metals", "BP monograph", "NMT 20 ppm"),
        ("Microbial limits", "BP monograph", "TAMC NMT 10^3 CFU/g"),
    ]
    return [
        SpecificationTest(
            test_name=name,
            method=method,
            acceptance_criterion=criterion,
            sort_order=i,
        )
        for i, (name, method, criterion) in enumerate(rows)
    ]
