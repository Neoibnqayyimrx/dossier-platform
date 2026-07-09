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

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def is_exportable(self) -> bool:
        # Export gate: no unresolved ERROR-severity findings.
        return len(self.errors) == 0

    def add(self, *findings: Finding) -> None:
        self.findings.extend(findings)


# A rule takes the project aggregate and returns 0+ findings.
Rule = Callable[["object"], list[Finding]]

_REGISTRY: list[tuple[str, Rule]] = []


def rule(rule_id: str):
    """Decorator to register a rule. WHY a registry: rules will grow to
    hundreds; registration keeps them decoupled and individually testable."""

    def deco(fn: Rule) -> Rule:
        _REGISTRY.append((rule_id, fn))
        return fn

    return deco


def run_all(project) -> Report:
    report = Report()
    for _rule_id, fn in _REGISTRY:
        report.add(*fn(project))
    return report
