"""Reading an acceptance criterion, and deciding whether a result meets it.

This is the parser rule R22 stands on, and it is kept in its own module for
one reason: **it is the part of P20 most likely to be wrong**, and it should
be readable and testable without a project, a database or a rule engine
around it.

## Why parse text at all

`SpecificationTest.acceptance_criterion` is a string on purpose (see
app/models/specification.py). Real criteria are heterogeneous -- ranges,
one-sided limits, qualitative conformance, conformance to a reference
spectrum -- and structured min/max columns would either drop the
qualitative half of every specification table or fill it with nulls. The
regulator reads the string; the applicant commits to the string.

So the parse is *advisory to the text*, never the other way round. That
ordering decides every judgement call below.

## The failure direction that matters

A false NEGATIVE -- failing to parse a criterion that a human can read --
costs an unchecked row, which this module reports honestly as unchecked.
A false POSITIVE -- reading "NMT 1.0 %" as a range of 1.0 to 1.0, say --
would either block a compliant submission or, far worse, pass a genuinely
out-of-specification batch. So every branch here returns `None` rather than
guessing, and `None` never means "passed".

There is no version of this module that silently approves a result it did
not understand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A number, optionally signed, with an optional decimal part. Used for both
# limits and results, so the two cannot disagree about what a number is.
_NUMBER = r"[-+]?\d+(?:[.,]\d+)?"

# "90.0 - 120.0 %", "90.0 to 120.0", "90.0-102.0 % w/w". The dash class
# covers the hyphen, the en dash and the em dash: a criterion typed in Word
# is very often not using the ASCII one, and treating an en dash as
# unparseable would leave real ranges unchecked.
_RANGE_RE = re.compile(
    rf"(?P<low>{_NUMBER})\s*(?:[-‐-―]|to)\s*(?P<high>{_NUMBER})",
    re.IGNORECASE,
)

# One-sided limits, in the spellings a specification actually uses.
# NMT = not more than, NLT = not less than -- pharmacopoeial shorthand,
# and the reason a general-purpose numeric parser would not do here.
_MAX_RE = re.compile(
    rf"(?:nmt|not\s+more\s+than|max(?:imum)?|below|<=|<|≤)\s*(?P<value>{_NUMBER})",
    re.IGNORECASE,
)
_MIN_RE = re.compile(
    rf"(?:nlt|not\s+less\s+than|min(?:imum)?|>=|>|≥)\s*(?P<value>{_NUMBER})",
    re.IGNORECASE,
)

_RESULT_NUMBER_RE = re.compile(_NUMBER)

# Words a qualitative result uses to say it passed, and to say it did not.
# The NEGATIVE list is checked first and is deliberately the more literal
# of the two: "does not comply" contains "comply", so a substring test in
# the wrong order would read a failure as a pass -- the single most
# dangerous bug this module could have.
_NON_CONFORMING = (
    "does not comply",
    "does not conform",
    "not complies",
    "non-compliant",
    "noncompliant",
    "fails",
    "failed",
    "fail",
    "out of specification",
    "oos",
)
_CONFORMING = (
    "complies",
    "conforms",
    "conform",
    "corresponds",
    "passes",
    "passed",
    "pass",
    "satisfactory",
)


@dataclass(frozen=True)
class NumericLimit:
    """A criterion reduced to bounds. Either bound may be absent."""

    low: float | None
    high: float | None

    def contains(self, value: float) -> bool:
        if self.low is not None and value < self.low:
            return False
        if self.high is not None and value > self.high:
            return False
        return True


def parse_limit(criterion: str) -> NumericLimit | None:
    """The numeric bounds a criterion states, or None if it states none.

    Order matters: a range is tried FIRST, because "90.0 - 120.0 %" also
    matches the one-sided patterns in some spellings, and reading a range
    as a single bound would silently drop half the limit.
    """
    if not criterion:
        return None

    match = _RANGE_RE.search(criterion)
    if match is not None:
        return NumericLimit(low=_to_float(match["low"]), high=_to_float(match["high"]))

    high = _MAX_RE.search(criterion)
    low = _MIN_RE.search(criterion)
    if high is None and low is None:
        return None
    return NumericLimit(
        low=_to_float(low["value"]) if low is not None else None,
        high=_to_float(high["value"]) if high is not None else None,
    )


def parse_result(result: str) -> float | None:
    """The number a reported result carries, or None if it carries none.

    Takes the FIRST number in the string. "99.4 % w/w" and "0.12 % (RRT
    0.8)" both mean their first number -- the trailing ones are units and
    identifiers, not the measurement -- and reading the last would turn a
    retention time into an assay.
    """
    if not result:
        return None
    match = _RESULT_NUMBER_RE.search(result)
    return None if match is None else _to_float(match.group(0))


def qualitative_verdict(result: str) -> bool | None:
    """True if a result says it conformed, False if it says it did not,
    None if it says neither.

    None is the ordinary case for a descriptive result ("White crystalline
    powder"), which is not a claim about conformance at all -- it is the
    observation the criterion has to be read against by a human. Saying so
    is more honest than pattern-matching a description against a
    description.
    """
    text = result.lower()
    if any(token in text for token in _NON_CONFORMING):
        return False
    if any(token in text for token in _CONFORMING):
        return True
    return None


def evaluate(criterion: str, result: str) -> bool | None:
    """Does `result` meet `criterion`? None means "cannot be decided here".

    The three outcomes are genuinely three, and collapsing the third into
    "passed" is the bug this whole module is shaped to avoid. A caller that
    treats None as a pass has thrown away the distinction between "checked
    and fine" and "nobody checked".
    """
    # A stated non-conformance is a failure whatever the numbers say: a
    # result reading "Fails" against a range is out of specification, and
    # the fact that no number could be parsed from it must not rescue it.
    verdict = qualitative_verdict(result)
    if verdict is False:
        return False

    limit = parse_limit(criterion)
    if limit is not None:
        value = parse_result(result)
        if value is None:
            # A numeric limit answered with a non-numeric result. Not a
            # pass and not a failure -- it is a mismatch a human has to
            # look at, which is exactly what None reports.
            return True if verdict else None
        return limit.contains(value)

    # No numeric limit: the criterion is qualitative ("Complies", "White to
    # off-white powder"), so only a qualitative verdict can settle it.
    return verdict


def _to_float(text: str) -> float:
    # Commas appear as decimal separators in criteria typed on a European
    # keyboard. Accepting both costs one replace and avoids reading "0,15"
    # as the integer 15 -- a hundredfold error, in the unsafe direction.
    return float(text.replace(",", "."))
