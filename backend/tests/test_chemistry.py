"""Tests for app.templating.chemistry: rendering a 2D structure image from
a SMILES string via RDKit, and failing loudly (not silently) on a SMILES
that doesn't parse -- a data-entry error, not a "not yet entered" state."""

from __future__ import annotations

import pytest

from app.templating.chemistry import InvalidSmilesError, render_structure_png

AMOXICILLIN_SMILES = "CC1(C)S[C@@H]2[C@H](NC(=O)[C@H](N)c3ccc(O)cc3)C(=O)N2[C@H]1C(=O)O"


def test_render_structure_png_returns_a_valid_png():
    data = render_structure_png(AMOXICILLIN_SMILES)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes


def test_render_structure_png_respects_size():
    small = render_structure_png(AMOXICILLIN_SMILES, size=(100, 80))
    large = render_structure_png(AMOXICILLIN_SMILES, size=(600, 500))
    assert len(large) > len(small)


def test_render_structure_png_rejects_invalid_smiles():
    with pytest.raises(InvalidSmilesError, match="not-a-real-smiles"):
        render_structure_png("not-a-real-smiles!!")
