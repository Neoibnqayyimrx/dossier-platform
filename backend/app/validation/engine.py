"""The deterministic rule engine.

A rule is a small, independently testable unit. The engine just runs every
registered rule against a project and aggregates the results. This is the
"regulatory intelligence" — and it is deterministic code, NOT the LLM. The
LLM-based reviewer (P10, later) sits on top as advisory-only and never replaces
these checks.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable

from app.models.enums import Region


class Severity(str, enum.Enum):
    ERROR = "ERROR"  # blocks export
    WARNING = "WARNING"  # allowed, but surfaced
    INFO = "INFO"
    # P10: the AI reviewer's ONLY allowed severity. Structural guarantee,
    # not a convention -- `errors()`/`is_exportable()` below only ever
    # look at ERROR, so an advisory finding is mechanically incapable of
    # gating an export, whether or not a caller remembers to filter it out.
    ADVISORY = "ADVISORY"


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    category: str
    message: str  # names the offending values — never just "inconsistent"
    section: str | None = None
    # P10: which layer produced this -- "data-rule" (P06, the default, so
    # every existing rule needs zero changes), "mechanical-ectd",
    # "external-validator", or "ai-reviewer". Lets one consolidated
    # Report merge all four without inventing a parallel report type.
    source: str = "data-rule"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def errors(self, overridden: frozenset[str] = frozenset()) -> list[Finding]:
        """ERROR-severity findings, excluding any rule id a human has
        overridden with a logged reason (see ValidationOverride, P06)."""
        return [
            f for f in self.findings if f.severity is Severity.ERROR and f.rule_id not in overridden
        ]

    def is_exportable(self, overridden: frozenset[str] = frozenset()) -> bool:
        # Export gate: no unresolved (i.e. non-overridden) ERROR findings.
        return len(self.errors(overridden)) == 0

    def by_category(self) -> dict[str, list[Finding]]:
        grouped: dict[str, list[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.category, []).append(finding)
        return grouped

    def add(self, *findings: Finding) -> None:
        self.findings.extend(findings)


# A rule takes the project aggregate and returns 0+ findings.
Rule = Callable[["object"], list[Finding]]

_REGISTRY: list[tuple[str, Rule, list[Region] | None]] = []
_TRIPWIRES: set[str] = set()


def rule(rule_id: str, regions: list[Region] | None = None, *, tripwire: bool = False):
    """Decorator to register a rule. WHY a registry: rules will grow to
    hundreds; registration keeps them decoupled and individually testable.

    `regions`, when given, restricts the rule to projects targeting one of
    those regions (e.g. a NAFDAC-specific certificate requirement) --
    `None` (the default) means the rule applies everywhere. The rule
    function itself never branches on region; filtering happens once,
    centrally, in `run_all`.

    `tripwire=True` (gap Phase 5b) declares a rule that CANNOT fire on data
    the platform produces today, by design, and runs anyway to catch the
    regression that would make it fire. It changes nothing about how the
    rule runs or what a finding means -- a tripped tripwire is an ordinary
    finding at its declared severity. What it changes is that the rule's
    status is stated in the registry rather than only in a docstring, so a
    list of the platform's checks can say which ones guard against a
    regression instead of implying live coverage they do not provide
    (the exact misreading the audit made of R31), and so a test can hold
    every tripwire silent on every seed dossier.
    """

    def deco(fn: Rule) -> Rule:
        _REGISTRY.append((rule_id, fn, regions))
        if tripwire:
            _TRIPWIRES.add(rule_id)
        return fn

    return deco


def tripwire_rule_ids() -> frozenset[str]:
    """The registered rules declared `tripwire=True`."""
    return frozenset(_TRIPWIRES)


def run_all(project) -> Report:
    report = Report()
    for _rule_id, fn, regions in _REGISTRY:
        if regions is not None and project.region not in regions:
            continue
        report.add(*fn(project))
    return report
