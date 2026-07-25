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


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    category: str
    message: str  # names the offending values — never just "inconsistent"
    section: str | None = None


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


def rule(rule_id: str, regions: list[Region] | None = None):
    """Decorator to register a rule. WHY a registry: rules will grow to
    hundreds; registration keeps them decoupled and individually testable.

    `regions`, when given, restricts the rule to projects targeting one of
    those regions (e.g. a NAFDAC-specific certificate requirement) --
    `None` (the default) means the rule applies everywhere. The rule
    function itself never branches on region; filtering happens once,
    centrally, in `run_all`.
    """

    def deco(fn: Rule) -> Rule:
        _REGISTRY.append((rule_id, fn, regions))
        return fn

    return deco


def run_all(project) -> Report:
    report = Report()
    for _rule_id, fn, regions in _REGISTRY:
        if regions is not None and project.region not in regions:
            continue
        report.add(*fn(project))
    return report
