"""Common CTD folder map, Modules 2-5 (P08).

WHY this is a plain hardcoded table, not region-profile config: Modules
2-5 are identical across ICH regions (nafdac-vs-fda-ema-scope.md -- "only
Module 1 is regional"). Only Module 1's document list and folder layout
varies, which is what `app.ctd.region_profiles` exists for.

Folder naming follows the same eCTD-style convention referenced in
reference/ectd-backbone-architecture.md (e.g. "m3/32-body-data") even
though NAFDAC's CTD has no XML backbone requirement -- reusing an
already-standard, human-readable layout costs nothing now and means P09's
eCTD backbone builder can point at the same physical files later.

WHY a lookup that raises on a miss, rather than falling back to some
guessed path: a new SECTIONS entry with no folder mapping here should fail
loudly at build time, not silently land in a made-up location a reviewer
would never find.
"""

from __future__ import annotations

MODULE_2_5_FOLDERS: dict[str, str] = {
    "2.3": "m2/23-quality-overall-summary",
    "3.2.P.1": "m3/32-body-data/32p/32p1-description-and-composition",
    "3.2.P.8.1": "m3/32-body-data/32p/32p8-stability/32p81-stability-summary-and-conclusion",
}


def folder_for_section(number: str) -> str:
    try:
        return MODULE_2_5_FOLDERS[number]
    except KeyError:
        raise KeyError(
            f"No CTD folder mapped for section {number!r} -- add it to "
            f"MODULE_2_5_FOLDERS (or to a region profile's module1_slots, "
            f"if it's a Module 1 document) before registering it in SECTIONS."
        )
