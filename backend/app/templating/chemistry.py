"""Render a 2D structural formula from a SMILES string (P04), via RDKit --
the standard cheminformatics toolkit for exactly this in pharma, rather
than sourcing a scanned or hand-drawn image.

WHY this raises rather than falling back to a blank image on a bad SMILES:
`ActiveIngredient.smiles` is structured data, same determinism-boundary
category as strength or dosage form -- a value that doesn't parse is a
data-entry error to fix at the source, not something to paper over with a
placeholder image (unlike a genuinely-missing Certificate, where a
placeholder is the honest state).
"""

from __future__ import annotations

import io

from rdkit import Chem
from rdkit.Chem import Draw


class InvalidSmilesError(ValueError):
    pass


def render_structure_png(smiles: str, size: tuple[int, int] = (500, 400)) -> bytes:
    """Return PNG bytes of the 2D structure encoded by `smiles`."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise InvalidSmilesError(f"{smiles!r} is not a valid SMILES string")

    image = Draw.MolToImage(mol, size=size)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
