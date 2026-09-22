"""gap Phase 5b: tripwire rules, declared as such.

A tripwire (`@rule(..., tripwire=True)`) cannot fire on data the platform
produces today, by design, and runs anyway to catch the regression that
would make it fire. Two claims follow, and each needs its own test:

- it IS silent on real data -- otherwise it is not a tripwire but a live
  rule mislabelled, and the label would hide real findings;
- it CAN fire -- otherwise it is dead code with a comment. That half is
  per-rule, because only the rule's author knows which regression to force
  (for R31, test_product_information.py's
  `test_r31_fires_when_a_second_copy_of_a_value_is_introduced`).

This file holds the first claim for every tripwire at once, so a rule
declared a tripwire tomorrow is held to it without anyone remembering to.
"""

from __future__ import annotations

import pytest

import app.validation.rules  # noqa: F401  registers every rule on import
from app.models import Region
from app.seed.amlodipine import build_amlodipine
from app.seed.ampiclox import build_ampiclox
from app.seed.examox import build_examox
from app.seed.fda import as_fda_original_application
from app.seed.lamox import build_lamox
from app.validation.engine import run_all, tripwire_rule_ids

# Every seed, clean AND with its planted defects: a tripwire must stay
# silent through the defects the other rules exist to catch, or it is
# reacting to something other than the regression it guards.
_SEEDS = {
    "examox": lambda: build_examox(buggy=False),
    "examox-buggy": lambda: build_examox(buggy=True),
    "lamox": lambda: build_lamox(buggy=False),
    "lamox-buggy": lambda: build_lamox(buggy=True),
    "ampiclox": lambda: build_ampiclox(buggy=False),
    "ampiclox-buggy": lambda: build_ampiclox(buggy=True),
    "amlodipine": build_amlodipine,
}


def test_r31_is_declared_a_tripwire():
    """The audit read R31 as "a silent no-op"; the registry now says what
    it is, so that reading cannot be made again from a list of checks."""
    assert "R31" in tripwire_rule_ids()


@pytest.mark.parametrize("seed", sorted(_SEEDS))
@pytest.mark.parametrize("region", ["NAFDAC", "EU", "FDA"])
def test_every_tripwire_is_silent_on_every_seed_in_every_region(seed, region):
    project = _SEEDS[seed]()
    if region == "FDA":
        as_fda_original_application(project)
    else:
        project.region = Region(region)
    tripped = [f for f in run_all(project).findings if f.rule_id in tripwire_rule_ids()]
    assert tripped == [], [f"{f.rule_id}: {f.message}" for f in tripped]
