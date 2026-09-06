"""Read `docs/target-toc.yaml` — the leaf-by-leaf contract for "what a
finished dossier is" (P16) — into the running application (P17).

WHY the app reads the target file at all, when P16 introduced it as a
document for a CI script to check against: because P17 needs the same three
facts the YAML already carries for every leaf — `applicable`, `condition`
and `not_applicable_reason` — in order to *emit* the not-applicable
statements those fields describe. The P17 prompt is explicit about the
alternative and why it loses: retyping the applicability of 98 leaves into
`region_profiles.py` by hand would create two truths, and the day they
disagree there is no way to tell which one the dossier was built from.

So the YAML stops being only a target and becomes config as well. That is a
promotion, not a compromise: it is a plain declarative table of regulatory
facts, versioned in the repo, re-confirmable against the agency's current
guideline — exactly what AGENTS.md §5 means by "config over hard-coding".

WHY module-level caching (`@lru_cache`): this is read once per process and
never changes underneath a running server. Re-parsing 98 entries on every
request to build a section list would be pure waste, and — worse — would
make it possible for two requests in one build to see different contracts
if someone edited the file mid-run.

This module deliberately sits ABOVE the layer folders (`ctd/`, `templating/`)
rather than inside one: both of those read it, and putting it in either
would mean the other importing across a layer boundary for a file that
belongs to neither.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

# backend/app/target_toc.py -> backend/app -> backend -> repo root
TARGET_TOC_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "target-toc.yaml"

# The `production` values that mean "this leaf IS a statement" -- see the
# YAML's own `production_types` block.
NA_STATEMENT_PRODUCTION = "na_statement"


@dataclass(frozen=True)
class TargetLeaf:
    """One entry from the target TOC's `sections` list.

    Only the fields the application actually consumes are lifted out; the
    rest (`notes`, `covers`, `data_sources`, `blocked_by`) stay in the YAML
    for the P16 check and for humans. `status` is deliberately NOT lifted:
    the YAML's own header says status is written by the audit, never read
    as an input.
    """

    number: str
    module: int
    title: str
    # "true" | "false" | "conditional", straight from the file. Kept as the
    # raw declaration; `app.ctd.region_profiles` is what turns it into an
    # `Applicability` for a given submission type.
    applicable: str
    production: str
    condition: str | None = None
    not_applicable_reason: str | None = None
    # P19: the axis this leaf repeats along, or None. Lifted out because
    # `test_registry_repeat_axes_match_the_target` holds the registry's
    # `SectionSpec.repeat` and this to the same string -- a contract that
    # only exists if both sides can be read from code.
    repeat: str | None = None

    @property
    def is_na_statement(self) -> bool:
        return self.production == NA_STATEMENT_PRODUCTION


def _normalise_applicable(raw: object, number: str) -> str:
    """YAML parses `applicable: false` as a bool and `conditional` as a str.

    Normalising to a string here rather than everywhere downstream keeps the
    three-state nature of this field visible: it is NOT a boolean with an
    odd extra value, it is a small vocabulary that happens to spell two of
    its members the way YAML spells booleans.
    """
    if isinstance(raw, bool):
        return "true" if raw else "false"
    if raw == "conditional":
        return "conditional"
    raise ValueError(
        f"Leaf {number!r} declares applicable={raw!r}; expected true, false or 'conditional'."
    )


@lru_cache(maxsize=1)
def load_target_leaves() -> tuple[TargetLeaf, ...]:
    """Every leaf in the target TOC, in file order (which is CTD order)."""
    with TARGET_TOC_PATH.open(encoding="utf-8") as fh:
        document = yaml.safe_load(fh)

    return tuple(
        TargetLeaf(
            number=entry["number"],
            module=entry["module"],
            title=entry["title"],
            applicable=_normalise_applicable(entry["applicable"], entry["number"]),
            production=entry["production"],
            condition=entry.get("condition"),
            not_applicable_reason=entry.get("not_applicable_reason"),
            repeat=entry.get("repeat"),
        )
        for entry in document["sections"]
    )


@lru_cache(maxsize=1)
def target_leaves_by_number() -> dict[str, TargetLeaf]:
    return {leaf.number: leaf for leaf in load_target_leaves()}


def na_statement_leaves() -> tuple[TargetLeaf, ...]:
    """The leaves whose whole content is a not-applicable statement.

    These are what `app.templating.registry` registers a SectionSpec for --
    one template, 14 sections. Driving that off the contract rather than a
    hand-written list means a new `production: na_statement` leaf in the
    YAML becomes producible by adding a folder mapping, not by remembering
    to edit the registry too.
    """
    return tuple(leaf for leaf in load_target_leaves() if leaf.is_na_statement)
