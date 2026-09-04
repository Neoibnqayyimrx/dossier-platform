"""Section *instances*: what actually gets rendered, once repetition exists.

Until P13 a registered section produced exactly one document, so a section
number ("3.2.P.1") was a sufficient identity everywhere -- narrative
lookup, leaf filename, folder, eCTD section key. **3.2.S breaks that.** It
is repeated per drug substance, so AMPICLOX (ampicillin + cloxacillin)
needs two complete copies of 3.2.S.1 and two of 3.2.S.4.1, and "3.2.S.1"
alone no longer names one document.

This module is the seam between "what sections exist" (the registry, which
stays a flat table of specs) and "what documents this project owes" (this
expansion, which depends on the project's data). Everything downstream --
assembly, CTD placement, the TOC, the eCTD backbone -- iterates instances
instead of registry keys.

WHY the subject's name is in the key and the folder rather than a bare
index (3.2.S.1-1, 3.2.S.1-2): an assessor navigating the package has to be
able to tell which substance a folder holds without opening it, and the
eCTD DTD makes the same choice -- `m3-2-s-drug-substance` carries a
required `substance` attribute, not a position.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.ctd.region_profiles import resolve_applicability
from app.templating.registry import SECTIONS, SectionSpec

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.project import Project

REPEAT_PER_DRUG_SUBSTANCE = "drug_substance"


def slugify_subject(name: str) -> str:
    """ "Ampicillin Sodium" -> "ampicillin-sodium". Used in folder names and
    leaf filenames, so it must be lowercase, ASCII-safe and stable: these
    strings end up in MD5-checksummed paths that have to be byte-identical
    across rebuilds (AGENTS.md 5)."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@dataclass(frozen=True)
class SectionInstance:
    """One document to produce."""

    spec: SectionSpec
    # The subject this copy is about, or None for a once-per-project
    # section. Typed loosely to keep this module free of a hard model
    # import -- the registry stays DB-agnostic, same as context.py.
    subject: "ActiveIngredient | None" = None

    @property
    def number(self) -> str:
        return self.spec.number

    @property
    def key(self) -> str:
        """Unique identity for this document: the narrative lookup key, the
        leaf filename stem, and the eCTD section key. Equal to the bare
        section number when the section doesn't repeat, so every pre-P13
        section keeps exactly the identity it already had -- no migration
        of stored narratives or sequence leaves is needed."""
        if self.subject is None:
            return self.number
        return f"{self.number}-{slugify_subject(self.subject.inn_name)}"

    @property
    def title(self) -> str:
        """Titles carry the subject too. Two PDFs both called "Specification"
        in one package is a bookmark list an assessor cannot use."""
        if self.subject is None:
            return self.spec.title
        return f"{self.spec.title} — {self.subject.inn_name}"


def expand_sections(project: "Project") -> list[SectionInstance]:
    """Every document `project` owes, in registry order.

    A repeating section with no subjects at all yields NO instances rather
    than an empty placeholder document: a product with no active ingredient
    recorded has nothing to say in 3.2.S, and P06's completeness rules are
    the right place to complain about that -- not a blank PDF that looks
    like an answer.
    """
    # P17: applicability is now DECLARED, so it is resolved once here and
    # consulted per section, rather than being implicit in which sections
    # happen to be registered.
    applicability = resolve_applicability(project)

    instances: list[SectionInstance] = []
    for spec in SECTIONS.values():
        if spec.is_statement:
            # A statement leaf exists only for a project that actually owes
            # the statement: the section is declared not applicable, or it
            # is conditional and the filer has answered "no". A project that
            # owes the section's real content, or that has not answered the
            # question yet, gets nothing here -- R19 is what complains about
            # the latter, and emitting a statement instead would put an
            # unmade claim into the dossier.
            resolved = applicability.get(spec.number)
            if resolved is not None and resolved.owes_statement:
                instances.append(SectionInstance(spec=spec))
            continue
        if spec.repeat_per == REPEAT_PER_DRUG_SUBSTANCE:
            instances.extend(
                SectionInstance(spec=spec, subject=api) for api in project.product.apis
            )
        elif spec.repeat_per is None:
            instances.append(SectionInstance(spec=spec))
        else:  # pragma: no cover - guards a typo in a future registry entry
            raise ValueError(f"Unknown repeat_per {spec.repeat_per!r} on section {spec.number}")
    return instances


def drug_substance_info(project: "Project") -> dict[str, tuple[str, str]]:
    """instance key -> (substance name, substance manufacturer name), for
    every section that repeats per drug substance.

    Exists because the ICH DTD declares BOTH attributes of
    `m3-2-s-drug-substance` as #REQUIRED. A drug substance cannot be filed
    anonymously: an assessor reading a combination product\'s dossier has
    to know whose specification this is and who made that material.

    Raises rather than substituting a placeholder when the manufacturer is
    missing -- a backbone naming the wrong maker of an API is a worse
    outcome than a failed build, and rule R17 already flags this at
    validation time, long before anything is assembled.
    """
    info: dict[str, tuple[str, str]] = {}
    for instance in expand_sections(project):
        if instance.subject is None:
            continue
        manufacturer = instance.subject.manufacturer
        if manufacturer is None:
            raise ValueError(
                f"{instance.subject.inn_name} has no manufacturer on file, but the eCTD "
                f"backbone requires one for every drug substance (see rule R17)"
            )
        info[instance.key] = (instance.subject.inn_name, manufacturer.name)
    return info
