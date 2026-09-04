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
    # P17: the not-applicable statements. They are placed in the folder the
    # section WOULD occupy, which is the entire point -- an assessor opening
    # m4 finds a document saying why there is nothing else there, instead of
    # an empty folder that looks like a packaging failure. The source dossier
    # does exactly this.
    "2.4": "m2/24-nonclinical-overview",
    "2.5": "m2/25-clinical-overview",
    "2.6": "m2/26-nonclinical-summary",
    "2.7": "m2/27-clinical-summary",
    "3.2.P.4.6": "m3/32-body-data/32p/32p4-control-of-excipients/32p46-novel-excipients",
    "3.2.A": "m3/32-body-data/32a-appendices",
    # ONE statement for the whole of Module 4, not one per 4.1/4.2/4.3 --
    # the source dossier files a single "Module 4 is not applicable" page,
    # and three near-identical statements would be three things an assessor
    # has to read to learn one fact. Hence the number "4.0", which is not a
    # real CTD section: it is this platform's name for the module-level
    # statement leaf, and the target TOC declares it as such.
    "4.0": "m4/40-not-applicable",
    "5.3.1.3": "m5/53-clinical-study-reports/531-biopharmaceutic-studies/5313-ivivc",
    "5.3.2": "m5/53-clinical-study-reports/532-pk-using-human-biomaterials",
    "5.3.3": "m5/53-clinical-study-reports/533-human-pk-studies",
    "5.3.4": "m5/53-clinical-study-reports/534-human-pd-studies",
    "5.3.5": "m5/53-clinical-study-reports/535-efficacy-and-safety-studies",
    "5.3.6": "m5/53-clinical-study-reports/536-postmarketing-experience",
    "5.3.7": "m5/53-clinical-study-reports/537-case-report-forms",
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
