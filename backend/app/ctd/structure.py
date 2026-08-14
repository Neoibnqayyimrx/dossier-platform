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


# Sections repeated per drug substance live under a per-substance folder,
# because "32s1-general-information" is not a unique location once a product
# has two actives. The substance name is in the path for the same reason the
# eCTD DTD puts it in a required attribute: an assessor must be able to tell
# which substance a folder holds without opening it.
DRUG_SUBSTANCE_FOLDERS: dict[str, str] = {
    "3.2.S.1": "32s1-general-information",
    "3.2.S.4.1": "32s4-control-of-drug-substance/32s41-specification",
}


def folder_for_section_instance(number: str, subject_slug: str | None) -> str:
    """The CTD folder for one section INSTANCE (app/templating/instances.py).

    Identical to `folder_for_section` for every section that appears once;
    repeated sections get a `32s-<substance>` folder of their own.

    Takes the slug rather than the instance object on purpose: this keeps
    P08's folder map from importing P07's assembly types, and means the
    only thing the CTD layer needs to know about repetition is "which
    subject, by name".
    """
    if subject_slug is None:
        return folder_for_section(number)
    try:
        tail = DRUG_SUBSTANCE_FOLDERS[number]
    except KeyError:
        raise KeyError(
            f"No drug-substance CTD folder mapped for section {number!r} -- "
            f"add it to DRUG_SUBSTANCE_FOLDERS before registering it in SECTIONS."
        )
    return f"m3/32-body-data/32s/32s-{subject_slug}/{tail}"


def folder_for_section(number: str) -> str:
    try:
        return MODULE_2_5_FOLDERS[number]
    except KeyError:
        raise KeyError(
            f"No CTD folder mapped for section {number!r} -- add it to "
            f"MODULE_2_5_FOLDERS (or to a region profile's module1_slots, "
            f"if it's a Module 1 document) before registering it in SECTIONS."
        )
