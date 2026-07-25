"""Tests for the P05 guardrails: numeric-leakage warnings (non-blocking)
and fabricated-citation rejection (blocking) — see app/narrative/
guardrails.py's docstring for why these have different severities."""

from __future__ import annotations

import pytest

from app.narrative.guardrails import (
    NarrativeGuardrailError,
    check_citations,
    check_numeric_leakage,
)


def test_numeric_leakage_flags_a_number_not_in_the_facts():
    facts = "Declared shelf life: 24 months."
    output = "This product remains stable for 999 months under all conditions."
    warnings = check_numeric_leakage(output, facts)
    assert len(warnings) == 1
    assert "999" in warnings[0]


def test_numeric_leakage_allows_numbers_present_in_the_facts():
    facts = "Declared shelf life: 24 months. Strength: 500 mg."
    output = "The 500 mg product supports its declared 24-month shelf life."
    assert check_numeric_leakage(output, facts) == []


def test_numeric_leakage_ignores_formatting_differences():
    # same value, different decimal formatting -- not a leak.
    facts = "Batch quantity: 144.00 kg."
    output = "The batch quantity was 144 kg."
    assert check_numeric_leakage(output, facts) == []


def test_check_citations_allows_a_retrieved_source():
    output = "Supported by prior findings. [Source: Q1A(R2) Step 4, 2003-02-06]"
    check_citations(output, ["Q1A(R2) Step 4, 2003-02-06"])  # must not raise


def test_check_citations_rejects_a_fabricated_source():
    output = "Per compendial requirements. [Source: USP 43 2020]"
    with pytest.raises(NarrativeGuardrailError, match="USP 43 2020"):
        check_citations(output, ["Q1A(R2) Step 4, 2003-02-06"])


def test_check_citations_allows_no_citations_at_all():
    check_citations("Plain prose with no citation marker.", ["Q1A(R2) Step 4, 2003-02-06"])
