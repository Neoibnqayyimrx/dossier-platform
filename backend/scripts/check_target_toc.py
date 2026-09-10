"""Compare docs/target-toc.yaml against what the platform can actually produce.

WHY this is a script and not just an audit prompt: an audit tells you the
coverage gap on the day someone remembers to run one. This tells you on every
push. It is the same move `folder_for_section` already makes -- fail loudly at
build time rather than silently ship a hole -- applied one level up, to the
question "does this dossier have every document it owes?"

Run (both spellings must give identical output -- see the sys.path pin below):
    uv run python scripts/check_target_toc.py            # report
    uv run python -m scripts.check_target_toc            # report
    uv run python scripts/check_target_toc.py --strict   # exit 1 on any gap

`--strict` IS CI, as of P24e. It was opt-in while coverage was incomplete --
"accurate but not useful", since a permanently red build teaches everyone to
ignore the build. Now that every leaf in the target has a route to
production, it stops being a progress report and becomes a contract: a new
`applicable` leaf with nowhere to come from fails the build that adds it.

What `--strict` fails on depends on the scope, and the distinction is the
whole point (see `is_gap`): without `--project` it asks whether the PLATFORM
can produce or place every leaf, and a placeholder passes because a route
exists; with `--project` it asks whether a FILING is complete, and a
placeholder is exactly the gap.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
TARGET_TOC = REPO_ROOT / "docs" / "target-toc.yaml"

# WHY this is pinned rather than left to the invocation: run as
# `python scripts/check_target_toc.py`, Python puts `scripts/` on sys.path and
# `app` does not import; run as `python -m scripts.check_target_toc` it puts
# `backend/` there and it does. Same script, two answers. A check whose result
# depends on how you spelled the command is not a check.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def load_target() -> dict:
    with TARGET_TOC.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def producible_keys(sections: list[dict]) -> set[str]:
    """Leaf numbers something in the platform can produce today.

    WHY this is not just `set(SECTIONS)`: the templating registry is one of
    three producers, and it is the only one that happens to be keyed by
    section number. Module 1 also comes from the region profile's
    `module1_slots` -- a slot backed by `declaration_types` is rendered by
    templating/declarations.py, one backed by `certificate_types` by
    templating/certificates.py. Reading only the registry reports 1.2.4-1.2.6
    as `missing` while they genuinely render, and reports the certificate
    slots as `missing` when they have folder placement and a placeholder.
    Both are wrong in the direction that hides real coverage.

    The leaf -> producer mapping stays in the YAML (`data_sources`), not here:
    the profile knows what a slot accepts, the target knows which leaf that
    is, and duplicating the leaf numbers into this script would give the
    contract a second, drifting copy.

    Raises if the app cannot be imported. Task 3 of P16: returning "unknown"
    for all 98 leaves and exiting 0 is a report that has checked nothing while
    looking like it checked everything.
    """
    try:
        from app.ctd.region_profiles import NAFDAC_PROFILE
        from app.ctd.structure import MODULE_2_5_FOLDERS, repeatable_section_numbers
        from app.ctd.toc import MODULE_TOC_LEAVES
        from app.templating.certificates import render_certificate_placeholder  # noqa: F401
        from app.templating.declarations import render_declaration  # noqa: F401
        from app.templating.registry import SECTIONS
    except Exception as exc:  # pragma: no cover - environment failure, not logic
        raise RuntimeError(
            "Cannot import the backend app, so no leaf status can be resolved. "
            "Run this from backend/ with the project environment: "
            "`uv run python -m scripts.check_target_toc`."
        ) from exc

    # SECTIONS carries P17's statement leaves too -- they are registered
    # like any other section, which is precisely the property that makes
    # them visible here with no special case.
    keys = set(SECTIONS)

    # P24: the per-module tables of contents. They are NOT in SECTIONS and
    # deliberately so -- a TOC is a function of the built package, not of
    # the project, so it has no template to register (see app/ctd/toc.py).
    # The map is imported rather than the four numbers retyped here, for
    # the same reason `data_sources` is read from the YAML below: a second
    # list of TOC leaves in this script is a second list that can disagree
    # with the builder.
    keys.update(MODULE_TOC_LEAVES)

    # A slot backed by a rendered section carries its own number.
    for slot in NAFDAC_PROFILE.module1_slots:
        if slot.section_number:
            keys.add(slot.section_number)

    # A slot backed by certificates or declarations has no single section
    # number -- it holds several leaves. The target says which, via
    # `data_sources`.
    backed_sources = set()
    if any(slot.certificate_types for slot in NAFDAC_PROFILE.module1_slots):
        backed_sources.add("Certificate")
    if any(slot.declaration_types for slot in NAFDAC_PROFILE.module1_slots):
        backed_sources.add("Declaration")

    for entry in sections:
        if entry["module"] != 1:
            continue
        if backed_sources.intersection(entry.get("data_sources") or []):
            keys.add(entry.get("registry_key") or entry["number"])

    # P18: an `uploaded` leaf is "producible" once the platform can PLACE a
    # file at it -- a declared folder (Modules 2-5, or a per-substance one)
    # or a Module 1 document slot. That is not the same as the document
    # being there, and `resolve_status` keeps the two apart: this makes the
    # leaf read `placeholder` rather than `missing`, and only a real
    # attachment in a real project makes it `done`.
    module1_document_leaves = {slot.section_number for slot in NAFDAC_PROFILE.document_slots}
    per_subject_leaves = repeatable_section_numbers()
    for entry in sections:
        if entry["production"] != "uploaded":
            continue
        number = entry["number"]
        if (
            number in MODULE_2_5_FOLDERS
            or number in per_subject_leaves
            or number in module1_document_leaves
        ):
            keys.add(entry.get("registry_key") or number)

    return keys


def resolve_status(entry: dict, producible: set[str], attached: set[str] = frozenset()) -> str:
    """The one place status is decided. Never hand-edited into the YAML.

    A leaf is DONE only if something can actually produce it. A producer alone
    is not enough for an `uploaded` leaf -- that renders a placeholder, which
    is exactly the state this check exists to make visible. Crediting a
    placeholder as a finished document would launder the platform's largest
    gap into a green tick.
    """
    key = entry.get("registry_key") or entry["number"]
    is_producible = key in producible
    production = entry["production"]

    if production == "uploaded":
        # P18. An uploaded leaf is DONE when, and only when, a real file has
        # actually been attached to it in a specific project -- which is why
        # `attached` has to be passed in and defaults to nothing. Coverage
        # with no project named is coverage of the PLATFORM ("could a file go
        # here"); coverage for a project is coverage of a FILING ("is the
        # paper in").
        if key in attached:
            return "done"
        # A slot for an uploaded leaf produces a placeholder, not the
        # document. Never DONE on a slot alone.
        return "placeholder" if is_producible else "missing"
    if production == "na_statement":
        # P17. WHY a statement counts as DONE while an `uploaded` leaf with
        # a slot does not: they are opposite cases that look alike. A CPP
        # placeholder is standing in for a document that must arrive from
        # outside and has not; a not-applicable statement IS the document --
        # there is nothing further to obtain, and the leaf is finished the
        # moment the platform can render it with its citation. Refusing to
        # credit it would leave the cheapest genuinely-complete leaves in
        # the dossier reading as gaps forever.
        return "done" if is_producible else "missing"
    if entry.get("blocked_by"):
        return "blocked"
    return "done" if is_producible else "missing"


# The two scopes this check can be run in, and the reason it needs two.
#
# PLATFORM (no --project): "does every leaf in the target have a route to
# production?" A `placeholder` IS a route -- the platform can place a file
# at that leaf, checksum it and refuse to export without it. What it cannot
# do is author a regulator's certificate, and it never will.
#
# PROJECT (--project <id>): "is this filing complete?" There a placeholder
# is exactly the gap: the CPP is not in.
PLATFORM, PROJECT = "platform", "project"

# P24e. Statuses that mean "no route to production" -- the strict gate's
# definition of failure in platform scope.
#
# WHY `placeholder` is NOT here, when P18 was so careful to keep it out of
# `done`: those are two different questions and P18's comment answers the
# other one. Crediting a placeholder as a finished DOCUMENT would launder
# the platform's largest gap -- and `resolve_status` still refuses to, so
# the report still prints 22 leaves as placeholders and a project-scoped
# run still counts them against the filing. What changes here is only what
# FAILS THE BUILD: a leaf whose document must arrive from outside has a
# complete route the day the upload path exists, and failing CI because
# nobody has attached a CPP to a hypothetical project would be a red build
# that no commit can turn green. That is the build everyone learns to
# ignore.
_NO_ROUTE = frozenset({"missing", "blocked"})


def is_gap(status: str, scope: str) -> bool:
    """Whether `status` fails the gate, in the scope being reported."""
    if scope == PROJECT:
        # "not-owed" is a filing's scoping ANSWER, not a hole in it. See
        # `not_owed_keys`.
        return status not in ("done", "not-owed")
    return status in _NO_ROUTE


def has_route(status: str) -> bool:
    """Whether the platform can produce or place this leaf at all."""
    return not is_gap(status, PLATFORM)


def attached_keys(project_id: str) -> set[str]:
    """Leaf keys that `project_id` has a real uploaded document for (P18).

    WHY the check grew a database mode at all: before P18 the question
    "what does this dossier still owe?" had one answer for the whole
    platform, because every leaf was either renderable or not. Uploads make
    the answer per-filing -- the platform can place a CPP at 1.2.7 for every
    project, and only this project knows whether the CPP is in. Reporting
    the platform's capability as though it were the filing's completeness is
    exactly the "looks complete, is not" failure P18 exists to remove.
    """
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings
    from app.models import SectionDocument

    async def _load() -> set[str]:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as conn:
                rows = await conn.execute(
                    select(SectionDocument.section_number, SectionDocument.subject_slug).where(
                        SectionDocument.project_id == project_id
                    )
                )
                return {f"{number}-{slug}" if slug else number for number, slug in rows.all()}
        finally:
            await engine.dispose()

    return asyncio.run(_load())


def not_owed_keys(project_id: str) -> set[str]:
    """Leaf numbers `project_id` legitimately does not owe (P24e).

    A conditional leaf the filer has answered "no" to is not a gap in that
    filing -- it is a scoping ANSWER. An applicant with no previous
    marketing authorization owes nothing at 1.2.13; one whose excipients are
    all compendial owes nothing at 3.2.P.4.3.

    WHY this had to be added the moment `--strict` went on: without it,
    project scope counted those leaves as missing paper and no correct
    filing could ever reach 98/98 -- so the number would have been unusable
    for the one question it exists to answer. Worse, it would have pushed a
    filer towards attaching SOMETHING at a leaf they had already correctly
    declared out of scope, which is how a dossier acquires a document
    contradicting its own scoping answers.

    This reads the same `resolve_applicability` the builders read, so the
    check cannot disagree with the package about what the filing owes.
    """
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings
    from app.ctd.region_profiles import resolve_applicability
    from app.models import Project

    async def _load() -> set[str]:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as conn:
                row = (
                    await conn.execute(
                        select(
                            Project.region,
                            Project.submission_type,
                            Project.condition_answers,
                        ).where(Project.id == project_id)
                    )
                ).first()
        finally:
            await engine.dispose()

        if row is None:
            raise SystemExit(f"No project {project_id!r}.")

        # A stand-in carrying only what resolve_applicability reads. Loading
        # the real ORM object would drag the whole product graph across an
        # async boundary for three scalar columns.
        class _Filing:
            region, submission_type, condition_answers = row

        return {
            number
            for number, decision in resolve_applicability(_Filing()).items()
            if not decision.is_applicable
        }

    return asyncio.run(_load())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="exit 1 on any gap")
    parser.add_argument(
        "--project",
        help=(
            "A project id. Reports that FILING's completeness -- uploaded leaves "
            "count as done once a document is attached -- rather than the "
            "platform's capability."
        ),
    )
    args = parser.parse_args()

    target = load_target()
    sections = target["sections"]
    producible = producible_keys(sections)
    attached = attached_keys(args.project) if args.project else frozenset()
    not_owed = not_owed_keys(args.project) if args.project else frozenset()

    by_module: dict[int, Counter] = defaultdict(Counter)
    by_production = Counter()
    blocker_counts = Counter()
    gaps: list[tuple[str, str, str]] = []

    scope = PROJECT if args.project else PLATFORM
    covered = 0
    placeholders = 0
    outstanding: set[str] = set()

    for entry in sections:
        status = resolve_status(entry, producible, attached)
        if entry["number"] in not_owed:
            # Scoped OUT by this filing's own answers, so it owes no
            # document. Reported as its own status rather than folded into
            # `done`: "we decided this does not apply" and "we filed it"
            # are different facts, and an assessor reads them differently.
            status = "not-owed"
        by_module[entry["module"]][status] += 1
        by_production[entry["production"]] += 1
        if status == "placeholder":
            placeholders += 1
        for blocker in entry.get("blocked_by", []):
            blocker_counts[blocker] += 1
            if is_gap(status, scope):
                outstanding.add(blocker)
        if is_gap(status, scope):
            gaps.append((entry["number"], entry["title"], status))
        else:
            covered += 1

    total = len(sections)

    print(f"TARGET: {target['meta']['name']}")
    print(f"Source: {target['meta']['derived_from']}")
    # Pasteable into the README verbatim -- progress that only exists in a
    # terminal is progress nobody outside this shell can see.
    label = f"project {args.project}" if args.project else "platform capability"
    print(f"\nCOVERAGE: {covered}/{total} leaves  ({label})\n")
    if scope == PLATFORM and placeholders:
        # Said out loud, every run. 98/98 in platform scope means "every
        # leaf has somewhere to come from", NOT "a dossier is complete" --
        # and a coverage number that let anyone believe the second thing
        # would be the most expensive sentence in this repo.
        print(
            f"  {placeholders} of those are uploaded leaves: the platform can place the "
            f"file,\n  and the file itself arrives per filing. Run with --project <id> "
            f"to ask\n  whether a particular dossier actually has them.\n"
        )

    print("By module:")
    for module in sorted(by_module):
        counts = by_module[module]
        line = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
        print(f"  Module {module}: {sum(counts.values()):>3} leaves  ({line})")

    print("\nBy production type:")
    for production, n in by_production.most_common():
        print(f"  {production:<14} {n:>3}")

    # P24e: this used to read "build these first", which stopped being true
    # the moment the last capability landed. A `blocked_by` is a permanent
    # record of what a leaf DEPENDS ON, not a to-do that deletes itself --
    # so the list stays and the heading now says which, if any, are still
    # outstanding. Silently dropping landed capabilities would erase the
    # dependency map that made the build order legible in the first place.
    print("\nLeaves by the capability they depend on:")
    for blocker, n in blocker_counts.most_common():
        state = "OUTSTANDING" if blocker in outstanding else "landed"
        print(f"  {blocker:<28} {n:>3} leaves  ({state})")

    if gaps:
        print(f"\n{len(gaps)} leaves not yet produced:")
        for number, title, status in gaps:
            print(f"  [{status:<11}] {number:<10} {title}")

    if args.strict and gaps:
        reason = (
            "have no route to production"
            if scope == PLATFORM
            else "are not yet filed for this project"
        )
        print(f"\nFAIL: {len(gaps)} applicable leaves {reason}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
