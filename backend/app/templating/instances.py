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

P19 generalised the axis. The drug substance was never special; it was
merely first. `REPEAT_AXES` below is the whole of the generalisation: an
axis says which collection on the project to expand over and what each
subject is CALLED, and everything else -- the key, the title, the slug, the
folder -- is derived from those two answers exactly as it was for 3.2.S.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from app.ctd.region_profiles import resolve_applicability
from app.models.enums import ManufacturerRole, PackagingRole
from app.templating.registry import SECTIONS, SectionSpec

if TYPE_CHECKING:
    from app.models.project import Project


def slugify_subject(name: str) -> str:
    """ "Ampicillin Sodium" -> "ampicillin-sodium". Used in folder names and
    leaf filenames, so it must be lowercase, ASCII-safe and stable: these
    strings end up in MD5-checksummed paths that have to be byte-identical
    across rebuilds (AGENTS.md 5)."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@dataclass(frozen=True)
class RepeatAxis:
    """One thing a section can be repeated ALONG.

    `subjects` answers "which rows of this project", `label` answers "what
    is this row called" -- and the label is load-bearing, not cosmetic: it
    becomes the instance key, the leaf filename, the folder name and the
    document title, so it must be the name a human would use to tell two
    subjects apart on an assessor's screen.

    WHY `subjects` filters rather than just returning a whole collection:
    two of the four axes are subsets of a collection that also holds rows
    belonging to a DIFFERENT axis. `product.manufacturers` holds the API
    maker alongside the finished-product sites, and 3.2.P.3.1 is about the
    drug product only -- naming the API site there files the wrong company
    as the maker of the medicine. Same for packaging and its role.
    """

    name: str
    subjects: Callable[["Project"], list]
    label: Callable[[object], str]


def _drug_product_sites(project: "Project") -> list:
    """Every site that makes, packs or is contracted for the FINISHED
    product -- which is every manufacturer except the API's.

    Expressed as an exclusion rather than as a list of the three included
    roles on purpose: a new ManufacturerRole member (a testing laboratory,
    say) is far more likely to belong in 3.2.P.3.1 than to be another kind
    of API site, so the default that follows from silence should be
    "listed", not "dropped from the dossier".
    """
    return [
        m for m in project.product.manufacturers if m.role is not ManufacturerRole.API_MANUFACTURER
    ]


def _drug_product_packs(project: "Project") -> list:
    """Every pack that is NOT the drug substance's.

    WHY the negative test, when 3.2.S.6's context uses the positive one:
    `Packaging.role` has a Python-side default, and SQLAlchemy applies
    those at FLUSH -- so an object built in memory and not yet committed
    (a seed, a test, an API create before the flush) still has `role is
    None`. Asking `is DRUG_PRODUCT` there would silently drop every pack
    from 3.2.P.7 and produce a dossier with no container closure system in
    it at all. Silence means the finished product, which is the same thing
    the migration's server_default says about the rows that predate the
    column. Claiming a pack is the API's, by contrast, has to be positive:
    that one is a statement about a material, not a default.
    """
    return [p for p in project.product.packaging if p.role is not PackagingRole.DRUG_SUBSTANCE]


def _pack_label(pack) -> str:
    """A pack's name for the key/folder: its component plus its material.

    WHY not the description: a description is a sentence ("Aluminium foil +
    PVC blister, 10 capsules per strip, 10 strips per carton"), and a folder
    named after a sentence is unreadable and fragile -- an edited comma
    would move the file. Component + material is short, and it is what
    actually distinguishes one pack from another.
    """
    parts = [pack.component.value]
    if pack.material:
        parts.append(pack.material)
    return " ".join(parts)


# Axis name -> how to resolve it. The names match the `repeat:` values the
# target TOC declares, and `test_every_repeat_axis_in_the_target_is_resolvable`
# holds the two together.
REPEAT_AXES: dict[str, RepeatAxis] = {
    "drug_substance": RepeatAxis(
        name="drug_substance",
        subjects=lambda project: list(project.product.apis),
        label=lambda api: api.inn_name,
    ),
    "manufacturing_site": RepeatAxis(
        name="manufacturing_site",
        subjects=_drug_product_sites,
        label=lambda site: site.name,
    ),
    "pack": RepeatAxis(
        name="pack",
        subjects=_drug_product_packs,
        label=_pack_label,
    ),
    # Declared, and deliberately unused so far: 3.2.P.4.1 (specification per
    # excipient) is still blocked by `spec_polymorphic_owner`, since
    # SpecificationTest is FK'd to active_ingredient and cannot yet belong
    # to an excipient. The axis is here because the target TOC names it, and
    # because the point of P19 is that adding that section becomes a
    # registry entry rather than another special case in this file.
    "excipient": RepeatAxis(
        name="excipient",
        subjects=lambda project: list(project.product.excipients),
        label=lambda excipient: excipient.name,
    ),
}


def get_repeat_axis(name: str) -> RepeatAxis:
    try:
        return REPEAT_AXES[name]
    except KeyError:
        raise KeyError(
            f"Unknown repeat axis {name!r}; known axes: {', '.join(sorted(REPEAT_AXES))}"
        )


@dataclass(frozen=True)
class SectionInstance:
    """One document to produce."""

    spec: SectionSpec
    # The subject this copy is about, or None for a once-per-project
    # section. Typed loosely to keep this module free of a hard model
    # import -- the registry stays DB-agnostic, same as context.py -- and
    # because since P19 a subject may be an active ingredient, a
    # manufacturing site, a pack or an excipient.
    subject: object | None = None

    @property
    def number(self) -> str:
        return self.spec.number

    @property
    def subject_name(self) -> str | None:
        """What this copy's subject is called, per its axis."""
        if self.subject is None:
            return None
        return get_repeat_axis(self.spec.repeat).label(self.subject)

    @property
    def subject_slug(self) -> str | None:
        name = self.subject_name
        return None if name is None else slugify_subject(name)

    @property
    def key(self) -> str:
        """Unique identity for this document: the narrative lookup key, the
        leaf filename stem, and the eCTD section key. Equal to the bare
        section number when the section doesn't repeat, so every pre-P13
        section keeps exactly the identity it already had -- no migration
        of stored narratives or sequence leaves is needed."""
        if self.subject is None:
            return self.number
        return f"{self.number}-{self.subject_slug}"

    @property
    def title(self) -> str:
        """Titles carry the subject too. Two PDFs both called "Specification"
        in one package is a bookmark list an assessor cannot use."""
        if self.subject is None:
            return self.spec.title
        return f"{self.spec.title} — {self.subject_name}"


def expand_sections(project: "Project") -> list[SectionInstance]:
    """Every document `project` owes, in registry order.

    A repeating section with no subjects at all yields NO instances rather
    than an empty placeholder document: a product with no active ingredient
    recorded has nothing to say in 3.2.S, and P06's completeness rules are
    the right place to complain about that -- not a blank PDF that looks
    like an answer. P19 kept that behaviour for every new axis, where it
    reads even more strongly: a project with no drug-substance packaging on
    file owes no 3.2.S.6 documents, and inventing one would describe a
    container closure system nobody declared.
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
        if spec.repeat is None:
            instances.append(SectionInstance(spec=spec))
            continue
        # get_repeat_axis raises on an unknown axis, which is the same
        # "fail loudly rather than guess" call folder_for_section makes: a
        # section that silently produced no instances would be a document
        # missing from the package with nothing to say so.
        axis = get_repeat_axis(spec.repeat)
        # SORTED by the subject's slug, and this is load-bearing rather than
        # tidy. None of these relationships declares an `order_by`, so the
        # order rows come back in is whatever the database chose -- and in
        # PostgreSQL an UPDATE physically moves a row, so a project edited
        # between two builds can hand them back in a different order. The
        # PATHS would survive that (they carry the subject's name, not an
        # index) but the package's file ORDER would not, and a zip whose
        # entries move is not byte-identical (AGENTS.md 5). Sorting by the
        # same string that names the folder makes the two orders one.
        expanded = [
            SectionInstance(spec=spec, subject=subject)
            for subject in sorted(
                axis.subjects(project), key=lambda s: slugify_subject(axis.label(s))
            )
        ]
        _reject_colliding_subjects(expanded)
        instances.extend(expanded)
    return instances


def _reject_colliding_subjects(instances: list[SectionInstance]) -> None:
    """Two subjects whose names slugify identically cannot both be filed.

    P19's first real casualty of generalising the axis. The drug substance
    never needed this check: two actives of one product have different INN
    names by construction, so "3.2.S.1-ampicillin" could not collide. Packs
    have no such guarantee -- two PRIMARY packs with no material recorded
    are both "pack-primary", which is one folder, one filename, and one
    document silently overwriting the other on the way into the package.

    Raising is the same call `folder_for_section` makes for an unmapped
    section, and for the same reason: a leaf lost at build time is a leaf
    nobody notices is missing until an assessor does.
    """
    seen: dict[str, SectionInstance] = {}
    for instance in instances:
        first = seen.get(instance.key)
        if first is not None:
            raise ValueError(
                f"Two subjects of {instance.number} are both named "
                f"{instance.subject_name!r} once slugified ({instance.key!r}), so one "
                f"would overwrite the other in the package. Give them distinguishing "
                f"detail -- a material, a site name -- before building."
            )
        seen[instance.key] = instance


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

    P19: the axis test is now explicit. Before, "has a subject" and
    "repeats per drug substance" were the same thing; a pack subject
    reaching this function would have been asked for an `inn_name` it does
    not have.
    """
    info: dict[str, tuple[str, str]] = {}
    for instance in expand_sections(project):
        if instance.spec.repeat != "drug_substance" or instance.subject is None:
            continue
        manufacturer = instance.subject.manufacturer
        if manufacturer is None:
            raise ValueError(
                f"{instance.subject.inn_name} has no manufacturer on file, but the eCTD "
                f"backbone requires one for every drug substance (see rule R17)"
            )
        info[instance.key] = (instance.subject.inn_name, manufacturer.name)
    return info


def repeat_element_info(project: "Project") -> dict[str, tuple[str, dict[str, str]]]:
    """instance key -> (axis name, eCTD element attributes), for every
    section filed under a REPEATING heading element.

    Two axes qualify today, and only two, because only two are starred in
    the ICH DTD:

      drug_substance  m3-2-s-drug-substance*          substance, manufacturer  #REQUIRED
      excipient       m3-2-p-4-control-of-excipients* excipient                #IMPLIED

    Every other repeating section (3.2.P.3.1 per site, 3.2.P.7 per pack)
    files several LEAVES under one heading instead, because its element is
    declared once with `leaf*` content. Placement and CTD folders answer to
    different authorities -- the folder tree still gives each subject its
    own directory, since that is how a human navigates it.

    WHY the excipient attribute is always set even though the DTD marks it
    #IMPLIED: two specification leaves under one heading, distinguishable
    only by filename, is a heading an assessor cannot read. The spec
    permits it; the dossier should not do it.
    """
    info: dict[str, tuple[str, dict[str, str]]] = {}
    for key, (substance, manufacturer) in drug_substance_info(project).items():
        info[key] = ("drug_substance", {"substance": substance, "manufacturer": manufacturer})

    for instance in expand_sections(project):
        if instance.spec.repeat != "excipient" or instance.subject is None:
            continue
        info[instance.key] = ("excipient", {"excipient": instance.subject.name})
    return info
