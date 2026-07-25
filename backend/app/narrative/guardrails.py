"""Guardrails for LLM-generated narrative (P05).

AGENTS.md §5's determinism boundary says numbers come from the data model,
never from LLM prose. These two checks enforce that from the *output* side,
as a second line of defense after prompting the model not to invent
figures or citations:

- **Numeric leakage** is a WARNING, not a block: flag any number in the
  output that wasn't in the facts we gave the model, for a human reviewer
  to look at. It's a warning rather than a hard block because a number
  can leak in harmlessly (e.g. the model writing "the 3 excipients" as a
  count, not a regulatory figure) — a human should judge that, not code.
- **Fabricated citations** are BLOCKED (raise): the model was told exactly
  which sources it may reference, in a fixed `[Source: ...]` marker
  format, so any marker naming something else is unambiguously wrong,
  not a judgment call.

WHY the leakage check compares against `facts_text` (the same rendered
facts string put in the prompt) rather than re-deriving allowed numbers
from the database: the whitelist must be "numbers this model was actually
told," not "any number that exists somewhere in the product's tables" —
the latter would let the model coincidentally match an unrelated field's
value and slip past the check.
"""

from __future__ import annotations

import re

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_CITATION_RE = re.compile(r"\[Source:\s*([^\]]+)\]")


class NarrativeGuardrailError(ValueError):
    """Raised when generated narrative cites a source that wasn't actually
    retrieved for it."""


def _numbers(text: str) -> set[float]:
    return {float(match) for match in _NUMBER_RE.findall(text)}


def check_numeric_leakage(output: str, facts_text: str) -> list[str]:
    """Return one warning string per number in `output` that doesn't appear
    among the numbers in `facts_text`."""
    allowed = _numbers(facts_text)
    leaked = sorted(_numbers(output) - allowed)
    return [
        f"number {n:g} appears in the generated text but not in the source facts" for n in leaked
    ]


def check_citations(output: str, allowed_sources: list[str]) -> None:
    """Raise `NarrativeGuardrailError` if `output` cites any source not in
    `allowed_sources` (the titles of documents actually retrieved)."""
    for cited in _CITATION_RE.findall(output):
        cited = cited.strip()
        if not any(cited == source or cited in source for source in allowed_sources):
            raise NarrativeGuardrailError(
                f"generated text cites {cited!r}, which was not among the "
                f"retrieved sources: {', '.join(allowed_sources) or '(none)'}"
            )
