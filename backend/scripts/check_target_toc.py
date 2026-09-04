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

`--strict` is for CI once coverage is complete. Until then it will fail every
run, which is accurate but not useful, so it is opt-in: a permanently red build
teaches everyone to ignore the build.
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

    return keys


def resolve_status(entry: dict, producible: set[str]) -> str:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="exit 1 on any gap")
    args = parser.parse_args()

    target = load_target()
    sections = target["sections"]
    producible = producible_keys(sections)

    by_module: dict[int, Counter] = defaultdict(Counter)
    by_production = Counter()
    blocker_counts = Counter()
    gaps: list[tuple[str, str, str]] = []

    for entry in sections:
        status = resolve_status(entry, producible)
        by_module[entry["module"]][status] += 1
        by_production[entry["production"]] += 1
        for blocker in entry.get("blocked_by", []):
            blocker_counts[blocker] += 1
        if status != "done":
            gaps.append((entry["number"], entry["title"], status))

    total = len(sections)
    done = sum(m["done"] for m in by_module.values())

    print(f"TARGET: {target['meta']['name']}")
    print(f"Source: {target['meta']['derived_from']}")
    # Pasteable into the README verbatim -- progress that only exists in a
    # terminal is progress nobody outside this shell can see.
    print(f"\nCOVERAGE: {done}/{total} leaves\n")

    print("By module:")
    for module in sorted(by_module):
        counts = by_module[module]
        line = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
        print(f"  Module {module}: {sum(counts.values()):>3} leaves  ({line})")

    print("\nBy production type:")
    for production, n in by_production.most_common():
        print(f"  {production:<14} {n:>3}")

    print("\nLeaves blocked, by capability (build these first):")
    for blocker, n in blocker_counts.most_common():
        print(f"  {blocker:<28} {n:>3} leaves")

    if gaps:
        print(f"\n{len(gaps)} leaves not yet produced:")
        for number, title, status in gaps:
            print(f"  [{status:<11}] {number:<10} {title}")

    if args.strict and gaps:
        print(f"\nFAIL: {len(gaps)} applicable leaves have no route to production.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
