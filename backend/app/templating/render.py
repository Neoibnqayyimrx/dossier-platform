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
from app.templating.instances import SectionInstance
from app.templating.registry import get_section

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
NO_STRUCTURE_PLACEHOLDER = "[[Structure not available — SMILES not yet entered for this API]]"


@dataclass
class StructureSlot:
    """One drug substance's structure block, as the QOS template loops over it.

    `image` is a docxtpl `InlineImage` when a SMILES is on file, and the
    placeholder *string* otherwise -- docxtpl renders either into the same
    `{{ s.image }}` position, so the template needs no conditional.
    """

    name: str
    image: InlineImage | str


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
    subject=None,
) -> RenderResult:
    """Render `section_number` for `project` and store the resulting .docx.

    `storage` defaults to the process-wide configured client (see
    `get_storage_client`); tests can still pass an explicit one for
    isolation, same as `embedding_client` is threaded through P03's ingest/
    retrieve functions rather than hard-coded to the cached singleton.
    """
    section = get_section(section_number)
    instance = SectionInstance(spec=section, subject=subject)
    context = build_context(section_number, project, narrative, subject=subject)

    template = DocxTemplate(section.template_path)
    if section.structure_images_slot:
        # A per-substance section shows ONLY its own substance's structure;
        # a whole-product section (2.3) shows every active's.
        subjects = [subject] if subject is not None else list(project.product.apis)
        context[section.structure_images_slot] = _build_structure_images(template, subjects)
    template.render(context)

    buffer = io.BytesIO()
    template.save(buffer)
    data = buffer.getvalue()

    storage = storage or get_storage_client()
    # instance.key equals section_number for non-repeating sections, so
    # existing storage keys are unchanged.
    key = f"projects/{project.id}/sections/{instance.key}.docx"
    storage.put(key, data, DOCX_CONTENT_TYPE)

    return RenderResult(section_number=instance.key, storage_key=key, size_bytes=len(data))


def _build_structure_images(template: DocxTemplate, subjects) -> list[StructureSlot]:
    """One structure block per drug substance in `subjects`, in order -- each with the API's name and either an embeddable image or a
    clearly-marked text placeholder if no SMILES is on file yet.

    WHY one per API rather than one per product: 2.3.S is repeated per drug
    substance (see `/reference/dossier-anatomy.md`), so a fixed-dose
    combination owes the assessor a structural formula for EACH active. The
    earlier version rendered `apis[0]` only, which meant AMPICLOX's QOS
    showed ampicillin and silently omitted cloxacillin -- a dossier that
    describes half the product, with nothing on the page to say so.

    WHY the name is emitted alongside every image, even for a single-API
    product: with two structures on the page an uncaptioned image is
    ambiguous, and an assessor cannot verify a structure they can't attach
    to a named substance.

    WHY a missing SMILES gets a soft placeholder but an invalid one doesn't
    (see `render_structure_png`'s `InvalidSmilesError`, left uncaught here):
    "not entered yet" is an expected, normal state -- same as any other
    empty narrative slot. "entered but unparseable" is a data-entry error
    in a structured field, the same category of problem as a malformed
    strength value, and should fail loudly rather than be silently papered
    over with a placeholder image.
    """
    slots: list[StructureSlot] = []
    for api in subjects:
        if api.smiles:
            png_bytes = render_structure_png(api.smiles)
            image: InlineImage | str = InlineImage(template, io.BytesIO(png_bytes), width=Mm(80))
        else:
            image = NO_STRUCTURE_PLACEHOLDER
        slots.append(StructureSlot(name=api.inn_name, image=image))
    return slots
