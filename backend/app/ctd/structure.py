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

from dataclasses import dataclass

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
    # P19: the sections whose data was already modelled and already
    # validated but which had no home. Each folder name follows the eCTD
    # element it corresponds to in ich-ectd-3-2.dtd, same as its neighbours.
    "3.2.P.3.2": "m3/32-body-data/32p/32p3-manufacture/32p32-batch-formula",
    "3.2.P.4.5": (
        "m3/32-body-data/32p/32p4-control-of-excipients/32p45-excipients-of-human-or-animal-origin"
    ),
    "3.2.P.6": "m3/32-body-data/32p/32p6-reference-standards",
    # 3.2.R is region-specific by definition (its CONTENT comes from the
    # region profile, see app.ctd.region_profiles.RegionProfile.
    # regional_information), but its PLACEMENT does not: the DTD declares
    # m3-2-r-regional-information for every region, and only what goes
    # inside it varies. So the folder belongs in this common map with the
    # rest of Module 3.
    # P20: the control-of-drug-product sections, plus the two excipient
    # sections that cover ALL excipients in one document (3.2.P.4.1 is the
    # one that repeats, so it lives in REPEAT_FOLDERS below instead).
    "3.2.P.4.2": ("m3/32-body-data/32p/32p4-control-of-excipients/32p42-analytical-procedures"),
    "3.2.P.4.4": (
        "m3/32-body-data/32p/32p4-control-of-excipients/32p44-justification-of-specifications"
    ),
    "3.2.P.5.1": "m3/32-body-data/32p/32p5-control-of-drug-product/32p51-specification",
    "3.2.P.5.2": ("m3/32-body-data/32p/32p5-control-of-drug-product/32p52-analytical-procedures"),
    "3.2.P.5.4": "m3/32-body-data/32p/32p5-control-of-drug-product/32p54-batch-analyses",
    "3.2.P.5.5": (
        "m3/32-body-data/32p/32p5-control-of-drug-product/32p55-characterisation-of-impurities"
    ),
    "3.2.P.5.6": (
        "m3/32-body-data/32p/32p5-control-of-drug-product/" "32p56-justification-of-specifications"
    ),
    "3.2.R": "m3/32-body-data/32r-regional-information",
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
    # P18: leaves whose content is an UPLOADED third-party artifact -- a
    # contract lab's validation report, a CRO's study report, a literature
    # pack. They have no template and never will (nobody here can author
    # them), but they still need a home, because a file with no declared
    # folder cannot be placed and `folder_for_section` raises rather than
    # guessing. Registering the folder is what makes the leaf attachable.
    "3.2.P.3.5": "m3/32-body-data/32p/32p3-manufacture/32p35-process-validation",
    "3.2.P.4.3": (
        "m3/32-body-data/32p/32p4-control-of-excipients/32p43-validation-of-analytical-procedures"
    ),
    "3.2.P.5.3": (
        "m3/32-body-data/32p/32p5-control-of-drug-product/32p53-validation-of-analytical-procedures"
    ),
    "3.3": "m3/33-literature-references",
    "5.3.1.1": "m5/53-clinical-study-reports/531-biopharmaceutic-studies/5311-bioavailability",
    "5.3.1.2": (
        "m5/53-clinical-study-reports/531-biopharmaceutic-studies/5312-comparative-ba-and-be"
    ),
    "5.3.1.4": (
        "m5/53-clinical-study-reports/531-biopharmaceutic-studies/5314-bioanalytical-methods"
    ),
    "5.4": "m5/54-literature-references",
}


# Sections repeated along an axis live under a per-subject folder, because
# "32s1-general-information" is not a unique location once a product has two
# actives -- nor is "32p7-container-closure-system" once it ships in three
# pack sizes. The subject's name is in the path for the same reason the eCTD
# DTD puts it in a required attribute: an assessor must be able to tell which
# substance, site or pack a folder holds without opening it.


@dataclass(frozen=True)
class RepeatFolders:
    """Where one repeat axis' instances live.

    The path is `base / f"{prefix}-{slug}" / tail`, with an empty tail
    dropped. Splitting it that way rather than storing whole paths keeps the
    per-subject segment in ONE place per axis: it is the segment that has to
    be identical across rebuilds for the checksums to hold, and a copy of it
    per section is a copy that can drift.
    """

    base: str
    prefix: str
    # section number -> the path BELOW the per-subject folder. Empty for an
    # axis whose sections are single leaves (a pack has no sub-structure).
    tails: dict[str, str]


REPEAT_FOLDERS: dict[str, RepeatFolders] = {
    "drug_substance": RepeatFolders(
        base="m3/32-body-data/32s",
        prefix="32s",
        tails={
            "3.2.S.1": "32s1-general-information",
            "3.2.S.4.1": "32s4-control-of-drug-substance/32s41-specification",
            # P18: uploaded per-substance artifacts. An elucidation-of-
            # structure report is about ONE active -- filing ampicillin's
            # spectra under a number that means "the drug substance" would
            # put the wrong molecule in front of an assessor, which is the
            # whole reason instances.py exists.
            "3.2.S.2.5": "32s2-manufacture/32s25-process-validation",
            "3.2.S.3.1": "32s3-characterisation/32s31-elucidation-of-structure",
            "3.2.S.4.3": (
                "32s4-control-of-drug-substance/32s43-validation-of-analytical-procedures"
            ),
            # P19.
            "3.2.S.2.1": "32s2-manufacture/32s21-manufacturer",
            "3.2.S.5": "32s5-reference-standards",
            "3.2.S.6": "32s6-container-closure-system",
            # P20. Each of these is about ONE substance -- a combination
            # product's two actives have two impurity profiles and two
            # batch histories, and filing either under a number that means
            # "the drug substance" puts the wrong material's numbers in
            # front of an assessor.
            "3.2.S.3.2": "32s3-characterisation/32s32-impurities",
            "3.2.S.4.2": "32s4-control-of-drug-substance/32s42-analytical-procedures",
            "3.2.S.4.4": "32s4-control-of-drug-substance/32s44-batch-analyses",
        },
    ),
    # P20: the excipient axis, declared by P19 and unused until
    # `SpecificationTest` could belong to an excipient. Only 3.2.P.4.1
    # repeats along it -- 3.2.P.4.2, 3.2.P.4.4 and 3.2.P.4.5 each cover
    # every excipient in one document and stay in MODULE_2_5_FOLDERS.
    "excipient": RepeatFolders(
        base="m3/32-body-data/32p/32p4-control-of-excipients",
        prefix="excipient",
        tails={"3.2.P.4.1": "32p41-specification"},
    ),
    "manufacturing_site": RepeatFolders(
        base="m3/32-body-data/32p/32p3-manufacture/32p31-manufacturers",
        prefix="site",
        tails={"3.2.P.3.1": ""},
    ),
    "pack": RepeatFolders(
        base="m3/32-body-data/32p/32p7-container-closure-system",
        prefix="pack",
        tails={"3.2.P.7": ""},
    ),
}


def repeatable_section_numbers() -> set[str]:
    """Every section number that has a per-subject folder, on any axis.

    Exists so callers that only need "can a repeated instance of this leaf
    be placed?" -- the upload endpoint, the target-TOC check -- ask one
    question instead of iterating the axis maps themselves.
    """
    return {number for folders in REPEAT_FOLDERS.values() for number in folders.tails}


def folder_for_section_instance(number: str, subject_slug: str | None) -> str:
    """The CTD folder for one section INSTANCE (app/templating/instances.py).

    Identical to `folder_for_section` for every section that appears once;
    a repeated section gets a folder of its own per subject.

    Takes the slug rather than the instance object on purpose: this keeps
    P08's folder map from importing P07's assembly types, and means the
    only thing the CTD layer needs to know about repetition is "which
    subject, by name".

    WHY it does not also take the axis name: the section number already
    determines it -- 3.2.S.1 repeats per substance and nothing else -- and
    a second parameter would be a second thing every caller has to thread
    through and could get wrong. A number mapped on two axes would be a
    contradiction, which `_folders_for` refuses rather than resolves.
    """
    if subject_slug is None:
        return folder_for_section(number)
    folders = _folders_for(number)
    tail = folders.tails[number]
    parts = [folders.base, f"{folders.prefix}-{subject_slug}"]
    if tail:
        parts.append(tail)
    return "/".join(parts)


def _folders_for(number: str) -> RepeatFolders:
    matches = [folders for folders in REPEAT_FOLDERS.values() if number in folders.tails]
    if not matches:
        raise KeyError(
            f"No per-subject CTD folder mapped for section {number!r} -- add it to the "
            f"right axis in REPEAT_FOLDERS before registering it as a repeating section."
        )
    if len(matches) > 1:
        # A number on two axes cannot be placed: "3.2.P.7 for ampicillin" and
        # "3.2.P.7 for the blister" would be two different paths for one
        # leaf. Raising here is the same call the miss above makes.
        raise KeyError(f"Section {number!r} is mapped on more than one repeat axis.")
    return matches[0]


def folder_for_section(number: str) -> str:
    try:
        return MODULE_2_5_FOLDERS[number]
    except KeyError:
        raise KeyError(
            f"No CTD folder mapped for section {number!r} -- add it to "
            f"MODULE_2_5_FOLDERS (or to a region profile's module1_slots, "
            f"if it's a Module 1 document) before registering it in SECTIONS."
        )
