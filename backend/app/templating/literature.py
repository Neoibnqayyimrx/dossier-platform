"""The literature reference lists, 3.3 and 5.4 (P24d).

## What these leaves are, and what this module does NOT do

3.3 and 5.4 hold literature: published papers, monograph extracts,
review articles. The papers themselves are `uploaded` in the target and
always will be -- nobody here can author someone else's journal article,
and the copyright rule in AGENTS.md 5 is emphatic that pharmacopoeial text
is not ours to reproduce.

What is generated is the **reference list** that ships beside the pack: a
statement of what the dossier relies on. It is registered with a
`leaf_suffix`, the same mechanism P22 used to file a bioequivalence
summary beside the CRO's report, so the list and the papers are two leaves
under one heading rather than one silently replacing the other.

## Why 3.3's list is derived rather than typed, which is the interesting half

A Module 3 literature list is the pharmacopoeial monographs and ICH
guidelines the quality case rests on. This dossier already says which
those are, in three places nobody thinks of as a bibliography:

  * every specification row names its `method` -- "BP monograph", "USP
    <711>", "ICH Q3B";
  * every impurity limit names its `limit_source`;
  * every material claims a `compendial_std`.

So the list is assembled from those, deduplicated. The consequence is the
one worth having: **3.3 cannot cite a standard the dossier does not rely
on, and cannot omit one it does.** A hand-typed bibliography does both
within a year -- a method is changed in 3.2.P.5.1 and the reference list
still names the monograph that was replaced.

CITATION, NEVER TEXT. This module emits the NAME of a monograph and never
a word of its content, which is the hard rule in AGENTS.md 5 and the same
line app/knowledge/ingest.py holds for the knowledge base. A reference
list is precisely the copyright-safe way to point at a pharmacopoeia.

## 5.4 is the clinical half

Module 5's literature is clinical: the published evidence a multisource
application cites where it is not filing its own study. That lives in
`ClinicalEntry` rows of kind `literature`, entered as free text -- and it
is printed here as entered, not parsed. Splitting "Smith et al., J Pharm
Sci 2019;108:1123" into authors, journal and year would mean GUESSING at
regulatory provenance from a string, and a citation this platform got
subtly wrong is worse than one it passed through untouched. A structured
Citation model is the right eventual shape; it needs the filer to enter
the fields, not a parser to invent them.
"""

from __future__ import annotations

import re

from app.models.enums import ClinicalKind
from app.templating.quality_control import specification_rows

# What a citation looks like inside a method or limit-source string.
#
# The strings this reads are written for a DIFFERENT purpose -- "HPLC, BP
# monograph" is an analytical method, and "ICH Q3C Class 2 limit" is a
# justification. Printing them verbatim as bibliography entries produced a
# list where "GC, ICH Q3C" was reference 4, which is not a reference. So
# the STANDARD is extracted and the entry says what cites it.
#
# WHY this is extraction and not the citation-parsing this module's
# docstring refuses to do: recognising the token "ICH Q3C" in a string is
# reading what the filer wrote. Splitting "Smith et al., J Pharm Sci
# 2019;108:1123" into authors, journal, volume and page is inferring a
# structure they never entered, and getting one field subtly wrong makes a
# citation that points somewhere else. One is a match; the other is a guess.
_CITATION_PATTERN = re.compile(
    r"""(
        ICH \s+ Q\d+[A-Z]? (?:\(R\d+\))?      # ICH Q3C, ICH Q1A(R2)
      | (?:Ph\.?\s*Eur\.?|European\ Pharmacopoeia)
      | USP (?:\s*<\d+>)?                      # USP, USP <711>
      | \bBP\b
      | \bJP\b
      | \bNF\b
      | \bWHO\b
      | \bISO\s*\d+
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _citations_in(text: str | None) -> set[str]:
    """Every external standard named in one method or limit-source string.

    A single string can name two: "GC, ICH Q3C" cites the guideline, and
    "HPLC, BP monograph" cites the pharmacopoeia. Returning a set means a
    method citing both appears under both.
    """
    if not text:
        return set()
    return {_normalise(match.group(1)) for match in _CITATION_PATTERN.finditer(text)}


def _normalise(citation: str) -> str:
    """One spelling per standard, so "Ph Eur" and "Ph. Eur." are one entry.

    Upper-cased except for the pharmacopoeia names that are conventionally
    mixed-case -- a bibliography reading "PH. EUR." looks like a mistake to
    the pharmacist who has to check it.
    """
    collapsed = " ".join(citation.split()).upper()
    if collapsed.startswith("PH") or collapsed.startswith("EUROPEAN"):
        return "Ph. Eur."
    return collapsed


def quality_references(product) -> list[dict[str, str]]:
    """3.3's list: what the quality case actually relies on.

    Each entry carries the leaf it is cited FROM, because a reference list
    whose entries cannot be traced back to a use is a reading list. An
    assessor querying "why is the BP monograph relevant here" should be
    able to see that 3.2.P.5.1 controls the product against it.
    """
    found: dict[str, set[str]] = {}

    def note(citation: str | None, cited_at: str) -> None:
        for standard in _citations_in(citation):
            found.setdefault(standard, set()).add(cited_at)

    for api in product.apis:
        if api.compendial_std:
            note(api.compendial_std.value, "3.2.S.4.1")
        for row in specification_rows(api):
            note(row.method, "3.2.S.4.1")
        for impurity in api.impurities:
            note(impurity.limit_source, "3.2.S.3.2")

    for excipient in product.excipients:
        if excipient.compendial_status:
            note(excipient.compendial_status.value, "3.2.P.4.1")
        for row in specification_rows(excipient):
            note(row.method, "3.2.P.4.1")

    for row in specification_rows(product):
        note(row.method, "3.2.P.5.1")
    for impurity in product.impurities:
        note(impurity.limit_source, "3.2.P.5.5")

    return [
        {"citation": citation, "cited_at": ", ".join(sorted(sections))}
        for citation, sections in sorted(found.items())
    ]


def literature_context(section, project) -> dict:
    """3.3 and 5.4 -- one builder, two modules, two sources.

    They share a shape (a numbered list of what the dossier cites) and
    differ in where the citations come from, which is the honest split: a
    quality reference is a standard the specification names, and a clinical
    reference is a paper the applicant chose to rely on.
    """
    product = project.product
    if section.number == "3.3":
        entries = quality_references(product)
        statement = (
            "The standards below are those this dossier's specifications, methods and "
            "impurity limits are drawn from. The list is generated from those sections, "
            "so it cannot cite a standard the dossier does not rely on, nor omit one it "
            "does. Monographs are CITED here and not reproduced."
        )
        empty = (
            "[[NO EXTERNAL STANDARD IS CITED anywhere in this dossier's specifications, "
            "methods or impurity limits. For a multisource product that is unusual -- "
            "check 3.2.S.4.1 and 3.2.P.5.1.]]"
        )
    else:
        entries = [
            {
                "citation": entry.summary.strip(),
                "cited_at": entry.reference_product or "Module 5",
            }
            for entry in product.clinical
            if entry.kind is ClinicalKind.LITERATURE
        ]
        statement = (
            "The published literature relied upon in Module 5. Each entry is filed as "
            "entered; the papers themselves are attached at this leaf."
        )
        empty = (
            "No published literature is relied upon in Module 5 for this application. "
            "The clinical evidence filed is the study reported at 5.3.1."
        )

    return {
        "section_number": section.number,
        "section_title": section.title,
        "product_name": product.brand_name,
        "statement": statement,
        "entries": entries,
        # WHY the empty case is a sentence and not an omitted table: a
        # reference list that is simply absent reads as an unfinished
        # dossier. One that says nothing is relied upon is a position the
        # applicant has taken, which an assessor can accept or query.
        "empty_statement": "" if entries else empty,
    }
