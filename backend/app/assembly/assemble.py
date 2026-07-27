"""Assembly orchestrator (P07): render every registered section, fill in
whatever approved narrative exists (P05), convert each to a deterministic
leaf PDF (this module's pdf.py), and gate the whole thing on P06's
validation report. The returned leaf inventory is the shared input P08
(CTD folder/TOC) and P09 (eCTD XML backbone) will both consume later.

WHY one PDF per registered section, never a merged module PDF: eCTD
granularity requires leaf-level documents (AGENTS.md's own P07 prompt is
explicit: "do NOT merge modules into mega-PDFs"). Iterating
`app.templating.registry.SECTIONS` one at a time and writing one leaf per
entry makes a merged mega-PDF structurally impossible to produce by
accident -- there's no code path here that concatenates two sections
together.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.assembly.pdf import convert_docx_to_pdf
from app.core.storage import StorageClient, get_storage_client
from app.models.project import Project
from app.narrative.context import get_approved_narrative
from app.templating.registry import SECTIONS
from app.templating.render import render_section
import app.validation.rules  # noqa: F401  registers every rule on import
from app.validation.engine import run_all

PDF_CONTENT_TYPE = "application/pdf"


class AssemblyBlockedError(RuntimeError):
    """Raised when the project has unresolved (non-overridden) validation
    errors -- AGENTS.md §5's export gate, extended to assembly."""


class LeafManifestEntry:
    def __init__(
        self, section: str, title: str, storage_path: str, md5: str, filename: str
    ) -> None:
        self.section = section
        self.title = title
        self.storage_path = storage_path
        self.md5 = md5
        self.filename = filename

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return (
            f"LeafManifestEntry(section={self.section!r}, title={self.title!r}, "
            f"storage_path={self.storage_path!r}, md5={self.md5!r})"
        )


async def assemble_project(
    db: AsyncSession,
    project: Project,
    *,
    overridden_rule_ids: frozenset[str] = frozenset(),
    storage: StorageClient | None = None,
) -> list[LeafManifestEntry]:
    """Render, fill, and convert every registered section for `project`
    into a leaf PDF, returning the leaf inventory. Raises
    `AssemblyBlockedError` and produces nothing at all if P06 reports any
    unresolved ERROR-severity finding.
    """
    report = run_all(project)
    if not report.is_exportable(overridden_rule_ids):
        blocking = [f.message for f in report.errors(overridden_rule_ids)]
        raise AssemblyBlockedError(
            "Cannot assemble: unresolved validation errors -- " + "; ".join(blocking)
        )

    storage = storage or get_storage_client()
    manifest: list[LeafManifestEntry] = []

    for number, section in SECTIONS.items():
        narrative = await get_approved_narrative(db, project.id, number)
        docx_result = render_section(number, project, narrative=narrative, storage=storage)
        docx_bytes = storage.get(docx_result.storage_key)

        pdf_bytes = convert_docx_to_pdf(docx_bytes, bookmark_title=section.title)
        md5 = hashlib.md5(pdf_bytes).hexdigest()
        filename = f"{number}.pdf"
        pdf_key = f"projects/{project.id}/leaves/{filename}"
        storage.put(pdf_key, pdf_bytes, PDF_CONTENT_TYPE)

        manifest.append(
            LeafManifestEntry(
                section=number,
                title=section.title,
                storage_path=pdf_key,
                md5=md5,
                filename=filename,
            )
        )

    return manifest
