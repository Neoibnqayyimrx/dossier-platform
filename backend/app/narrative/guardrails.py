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
- **Register violations** (P23) are WARNINGS here and a WARNING at export
  (rule R33): a patient information leaflet has a plain-language
  obligation an SmPC does not, so text drafted for 1.3.3 is checked
  against a different standard than text drafted for 1.3.1. See
  `check_patient_register` for what that standard is and why it is not a
  hard block.

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


# ---- P23: the patient register ---------------------------------------------
#
# A patient information leaflet is not an SmPC with simpler words bolted on.
# It is a legally distinct document with a readability obligation: in the EU
# it must pass user testing on real readers, and NAFDAC's guidance asks for
# language "readily understandable by the patient". "Contraindicated in
# severe hepatic impairment" is correct, precise, and a failure.
#
# WHY these three checks and not a readability index (Flesch-Kincaid and
# friends): a reading-grade formula counts syllables, so it scores
# "paracetamol" as hard and "may cause death" as easy, and it cannot tell a
# filer WHAT to change. Each check below names the offending phrase and, for
# jargon, the word to use instead -- which is the difference between a score
# and a correction.

# Technical term -> what a leaflet says instead. Every entry is a term that
# is CORRECT in an SmPC, which is the point: this is not a list of mistakes,
# it is a translation table between two registers.
PATIENT_JARGON: dict[str, str] = {
    "contraindicated": "must not be used",
    "contraindication": "reason not to take this medicine",
    "adverse reaction": "side effect",
    "adverse event": "side effect",
    "undesirable effect": "side effect",
    "hypersensitivity": "allergic reaction",
    "administer": "take",
    "administered": "taken",
    "administration": "taking this medicine",
    "posology": "dose",
    "hepatic": "liver",
    "renal": "kidney",
    "concomitant": "at the same time",
    "concomitantly": "at the same time",
    "excipient": "other ingredient",
    "efficacy": "how well it works",
    "pharmacokinetic": "how the body handles the medicine",
    "pharmacodynamic": "how the medicine works",
    "prophylaxis": "prevention",
    "antipyretic": "medicine that lowers fever",
    "analgesia": "pain relief",
    "oedema": "swelling",
    "pruritus": "itching",
    "urticaria": "a raised itchy rash",
    "dyspepsia": "indigestion",
    "somnolence": "feeling sleepy",
    "therapy": "treatment",
    "indicated for": "used to treat",
    "discontinue": "stop taking",
    "titrate": "change the dose slowly",
}

# The longest sentence a leaflet should carry. Not a folklore number: the
# plain-language guidance behind the EU readability template asks for short
# sentences carrying one idea, and 25 words is where a sentence reliably
# stops carrying one. It is a WARNING threshold, not a rejection -- a
# 26-word sentence is a suggestion to a human, not an error.
MAX_LEAFLET_SENTENCE_WORDS = 25

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_PLACEHOLDER_RE = re.compile(r"\[\[.*?\]\]")


def _sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation followed by whitespace.

    Deliberately naive, and the naivety is bounded: this runs on leaflet
    prose, where "e.g." and decimal points are exactly what the register
    check is asking the writer to avoid anyway. A mis-split can only
    produce a shorter sentence, which can only make this check quieter --
    it can never invent a violation.
    """
    stripped = _PLACEHOLDER_RE.sub("", text)
    return [sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(stripped) if sentence.strip()]


def check_patient_register(output: str) -> list[str]:
    """Return one warning per way `output` reads like an SmPC rather than a
    leaflet.

    WARNINGS, not a raise, and the line is the same one numeric leakage
    sits on: a fabricated citation is unambiguously wrong, while "this
    sentence is too long for a patient" is a judgement a human should make.
    Blocking generation on it would also make the failure invisible -- the
    filer would see an error and no draft, instead of a draft with the
    three phrases to fix named on it.

    Rule R33 re-runs this at export on the APPROVED text, which is where it
    becomes a gate: text a human read and approved with "contraindicated"
    still in it is a leaflet about to be filed.
    """
    warnings: list[str] = []
    lowered = output.lower()

    for term, plain in PATIENT_JARGON.items():
        # Word-boundary matched, so "administration" does not also fire the
        # "administer" entry and "therapy" does not fire inside
        # "chemotherapy" -- a warning naming a word that is not there is
        # how a check teaches people to ignore it.
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            warnings.append(
                f"patient leaflet uses the technical term {term!r}; a leaflet says " f"{plain!r}"
            )

    for sentence in _sentences(output):
        words = sentence.split()
        if len(words) > MAX_LEAFLET_SENTENCE_WORDS:
            warnings.append(
                f"patient leaflet sentence is {len(words)} words "
                f"(limit {MAX_LEAFLET_SENTENCE_WORDS}): {' '.join(words[:8])}..."
            )

    # A leaflet addresses the reader. One that never says "you" or "your"
    # has been written ABOUT the patient rather than TO them, which is the
    # single most reliable sign that SmPC text was pasted across.
    if output.strip() and not re.search(r"\byou\b|\byour\b", lowered):
        warnings.append(
            "patient leaflet text never addresses the reader as 'you' -- it is "
            "written about the patient rather than to them"
        )

    return warnings
