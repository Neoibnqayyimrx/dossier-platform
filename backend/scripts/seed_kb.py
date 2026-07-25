"""Seed the knowledge base with real ICH guideline PDFs (P03 task 5).

Ingests two genuine ICH harmonised tripartite guidelines, fetched from the
official ICH database and checked into reference/kb_sources/ich/ (verified
by extracting real text with pypdf — not fabricated placeholder content):

- Q1A(R2) — Stability Testing of New Drug Substances and Products
  https://database.ich.org/sites/default/files/Q1A(R2)%20Guideline.pdf
- M4Q(R1) — CTD for Registration of Pharmaceuticals: Quality (QOS of
  Module 2 / Module 3)
  https://database.ich.org/sites/default/files/M4Q_R1_Guideline.pdf

Idempotent via ingest_document's own (source, title, version) replace
logic: re-running updates the same two documents rather than duplicating.

Run with the API's dependencies available, e.g.:
    cd backend && uv run python -m scripts.seed_kb

(-m, not a bare file path: running "python scripts/seed_kb.py" directly
puts scripts/ on sys.path instead of backend/, so `from app...` imports
fail with ModuleNotFoundError.)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pypdf

from app.core.config import get_settings
from app.core.db import async_session_factory
from app.knowledge.embeddings import get_embedding_client
from app.knowledge.ingest import ingest_document

KB_SOURCES = Path(__file__).resolve().parent.parent.parent / "reference" / "kb_sources" / "ich"

DOCUMENTS = [
    {
        "path": KB_SOURCES / "Q1A_R2_stability_testing.pdf",
        "source": "ICH",
        "title": "Q1A(R2) Stability Testing of New Drug Substances and Products",
        "version": "Step 4, 2003-02-06",
        "license": "ich-harmonised-guideline",
        "url": "https://database.ich.org/sites/default/files/Q1A(R2)%20Guideline.pdf",
        "jurisdiction": "ICH",
    },
    {
        "path": KB_SOURCES / "M4Q_R1_ctd_quality.pdf",
        "source": "ICH",
        "title": "M4Q(R1) CTD for Registration of Pharmaceuticals: Quality",
        "version": "Step 4, 2002-09-12",
        "license": "ich-harmonised-guideline",
        "url": "https://database.ich.org/sites/default/files/M4Q_R1_Guideline.pdf",
        "jurisdiction": "ICH",
    },
]


def _extract_text(pdf_path: Path) -> str:
    reader = pypdf.PdfReader(str(pdf_path))
    return "\n\n".join(page.extract_text() for page in reader.pages)


async def main() -> None:
    settings = get_settings()
    embedding_client = get_embedding_client()

    async with async_session_factory() as session:
        for doc in DOCUMENTS:
            text = _extract_text(doc["path"])
            result = await ingest_document(
                session,
                embedding_client,
                source=doc["source"],
                title=doc["title"],
                version=doc["version"],
                license=doc["license"],
                url=doc["url"],
                jurisdiction=doc["jurisdiction"],
                text=text,
                chunk_max_chars=settings.kb_chunk_max_chars,
            )
            action = "updated" if result.was_update else "created"
            print(f"{action}: {doc['title']!r} -> {result.chunks_created} chunks")


if __name__ == "__main__":
    asyncio.run(main())
