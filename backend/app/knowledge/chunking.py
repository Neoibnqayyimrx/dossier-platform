"""Heading-aware text chunker for the knowledge base (P03).

WHY chunk by heading rather than a fixed character stride: a fixed-size
slider would happily cut a chunk in half mid-clause and mix text from two
different guideline sections into one embedding — bad for both retrieval
quality and citation (P03's whole point is that a retrieved chunk can be
traced to a section, not just "somewhere in this PDF"). Detecting headings
and carrying the current one as `section_label` on every chunk under it is
what makes that citation possible.

WHY line-by-line rather than blank-line-delimited paragraphs: PDF text
extraction (pypdf) inserts a newline per *visual* line, not per paragraph —
a heading is often followed immediately by its body text with no blank
line, and a single sentence is broken across several lines. Reflowing
line-by-line (joining non-heading lines with spaces) both finds headings
that a paragraph-blank-line split would miss and undoes the mid-sentence
wrapping so chunks read as continuous prose.

This is a heuristic, not a PDF-structure parser: ICH-style guidelines
consistently use short numbered ("2.1.7 Storage Conditions") or ALL-CAPS
lines as headings, which is enough to get useful section labels out of
plain extracted text — it will occasionally misfire on a short ALL-CAPS
acronym-heavy sentence, which is an acceptable false positive for a first
pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBERED_HEADING_RE = re.compile(r"^\d+(\.\d+){0,4}\.?\s+\S.{0,100}$")
_MAX_HEADING_WORDS = 12


@dataclass
class Chunk:
    text: str
    section_label: str | None


def _looks_like_heading(line: str) -> bool:
    if not line or len(line) > 120:
        return False
    if _NUMBERED_HEADING_RE.match(line):
        return True
    words = line.split()
    if len(words) <= _MAX_HEADING_WORDS and line == line.upper() and any(c.isalpha() for c in line):
        return True
    return False


def chunk_text(text: str, max_chars: int) -> list[Chunk]:
    """Split `text` into chunks of at most `max_chars`, tagging each with
    the most recent heading line seen above it (or None if none yet)."""
    chunks: list[Chunk] = []
    section_label: str | None = None
    buffer: list[str] = []
    buffer_len = 0

    def flush() -> None:
        nonlocal buffer, buffer_len
        if buffer:
            chunks.append(Chunk(text=" ".join(buffer), section_label=section_label))
            buffer = []
            buffer_len = 0

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if _looks_like_heading(line):
            flush()
            section_label = line[:120]
            continue
        if buffer and buffer_len + len(line) > max_chars:
            flush()
        buffer.append(line)
        buffer_len += len(line) + 1

    flush()
    return chunks
