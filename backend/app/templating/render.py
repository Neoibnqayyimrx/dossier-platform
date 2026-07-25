"""Renderer for the template engine (P04): section template + context ->
a `.docx` in object storage.

WHY return a storage key/handle rather than raw bytes: callers (tests now,
P07/P08 assembly later) shouldn't need to know or care whether the bytes
live in an in-memory dict or a real MinIO bucket -- `StorageClient` (P03's
embedding-client pattern, again) is the only thing that knows that. Handing
back a key keeps the renderer itself storage-agnostic.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from app.core.storage import StorageClient, get_storage_client
from app.models.project import Project
from app.templating.chemistry import render_structure_png
from app.templating.context import build_context
from app.templating.registry import get_section

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
NO_STRUCTURE_PLACEHOLDER = "[[Structure not available — SMILES not yet entered for this API]]"


@dataclass
class RenderResult:
    section_number: str
    storage_key: str
    size_bytes: int


def render_section(
    section_number: str,
    project: Project,
    narrative: dict[str, str] | None = None,
    storage: StorageClient | None = None,
) -> RenderResult:
    """Render `section_number` for `project` and store the resulting .docx.

    `storage` defaults to the process-wide configured client (see
    `get_storage_client`); tests can still pass an explicit one for
    isolation, same as `embedding_client` is threaded through P03's ingest/
    retrieve functions rather than hard-coded to the cached singleton.
    """
    section = get_section(section_number)
    context = build_context(section_number, project, narrative)

    template = DocxTemplate(section.template_path)
    if section.structure_image_slot:
        context[section.structure_image_slot] = _build_structure_image(template, project)
    template.render(context)

    buffer = io.BytesIO()
    template.save(buffer)
    data = buffer.getvalue()

    storage = storage or get_storage_client()
    key = f"projects/{project.id}/sections/{section_number}.docx"
    storage.put(key, data, DOCX_CONTENT_TYPE)

    return RenderResult(section_number=section_number, storage_key=key, size_bytes=len(data))


def _build_structure_image(template: DocxTemplate, project: Project) -> InlineImage | str:
    """Return an embeddable structure image for the project's (first) API,
    or a clearly-marked text placeholder if no SMILES is on file yet.

    WHY a missing SMILES gets a soft placeholder but an invalid one doesn't
    (see `render_structure_png`'s `InvalidSmilesError`, left uncaught here):
    "not entered yet" is an expected, normal state -- same as any other
    empty narrative slot. "entered but unparseable" is a data-entry error
    in a structured field, the same category of problem as a malformed
    strength value, and should fail loudly rather than be silently papered
    over with a placeholder image.
    """
    apis = project.product.apis
    smiles = apis[0].smiles if apis else None
    if not smiles:
        return NO_STRUCTURE_PLACEHOLDER
    png_bytes = render_structure_png(smiles)
    return InlineImage(template, io.BytesIO(png_bytes), width=Mm(80))
