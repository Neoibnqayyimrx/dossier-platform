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
from app.templating.instances import expand_sections, slugify_subject
from app.target_toc import target_leaves_by_number
from app.templating.render import render_section
import app.validation.rules  # noqa: F401  registers every rule on import
from app.validation.engine import run_all

PDF_CONTENT_TYPE = "application/pdf"


class AssemblyBlockedError(RuntimeError):
    """Raised when the project has unresolved (non-overridden) validation
    errors -- AGENTS.md §5's export gate, extended to assembly.

    P18 gave it the findings themselves, not just a joined sentence. Once a
    quarter of the dossier is uploaded paper, "blocked" is the ORDINARY
    state of a filing in progress rather than an exceptional one, and the
    useful answer is "these four leaves are waiting on a document" -- which
    the UI can link to -- rather than a paragraph the user has to read and
    translate back into a list of things to go and do.
    """

    def __init__(self, message: str, findings: list | None = None) -> None:
        super().__init__(message)
        self.findings = findings or []


class LeafManifestEntry:
    def __init__(
        self,
        section: str,
        title: str,
        storage_path: str,
        md5: str,
        filename: str,
        section_number: str | None = None,
        subject_slug: str | None = None,
    ) -> None:
        self.section = section  # the INSTANCE key ("3.2.S.1-ampicillin")
        self.title = title
        self.storage_path = storage_path
        self.md5 = md5
        self.filename = filename
        # The registry number and (for repeated sections) which subject this
        # copy is about. Carried so P08/P09 can place the leaf without having
        # to re-derive the split from the key string, and without P07
        # importing either layer's folder map.
        self.section_number = section_number or section
        self.subject_slug = subject_slug

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
        blocking = report.errors(overridden_rule_ids)
        raise AssemblyBlockedError(
            "Cannot assemble: unresolved validation errors -- "
            + "; ".join(f.message for f in blocking),
            findings=blocking,
        )

    storage = storage or get_storage_client()
    manifest: list[LeafManifestEntry] = []

    # P18: the real files a human has attached, keyed the same way a
    # rendered document is (see SectionDocument.instance_key). An uploaded
    # file WINS over a rendered one for the same leaf -- if someone has
    # attached the actual signed, stamped document, a generated version of
    # it is not an improvement on it.
    uploaded = {document.instance_key: document for document in project.documents}

    for instance in expand_sections(project):
        document = uploaded.pop(instance.key, None)
        if document is not None:
            # An uploaded PDF is ALREADY a leaf. It is not re-rendered and
            # not re-converted: its stored MD5 was computed over these exact
            # bytes at upload time (app/documents/ingest.py), and the whole
            # point of a checksum is that it describes the file that ships.
            manifest.append(
                LeafManifestEntry(
                    section=instance.key,
                    title=instance.title,
                    section_number=instance.number,
                    subject_slug=(
                        slugify_subject(instance.subject.inn_name)
                        if instance.subject is not None
                        else None
                    ),
                    storage_path=document.storage_key,
                    md5=document.md5,
                    filename=f"{instance.key}.pdf",
                )
            )
            continue

        # Narratives are keyed by INSTANCE, not section number: ampicillin's
        # 3.2.S.1.3 prose is not cloxacillin's, and storing one approved
        # narrative for "3.2.S.1" would silently put the same paragraph
        # under both substances.
        narrative = await get_approved_narrative(db, project.id, instance.key)
        docx_result = render_section(
            instance.number,
            project,
            narrative=narrative,
            storage=storage,
            subject=instance.subject,
        )
        docx_bytes = storage.get(docx_result.storage_key)

        pdf_bytes = convert_docx_to_pdf(docx_bytes, bookmark_title=instance.title)
        md5 = hashlib.md5(pdf_bytes).hexdigest()
        filename = f"{instance.key}.pdf"
        pdf_key = f"projects/{project.id}/leaves/{filename}"
        storage.put(pdf_key, pdf_bytes, PDF_CONTENT_TYPE)

        manifest.append(
            LeafManifestEntry(
                section=instance.key,
                title=instance.title,
                section_number=instance.number,
                subject_slug=(
                    slugify_subject(instance.subject.inn_name)
                    if instance.subject is not None
                    else None
                ),
                storage_path=pdf_key,
                md5=md5,
                filename=filename,
            )
        )

    # Whatever is left is an uploaded document for a leaf the registry does
    # not know about -- which is most of them. A CRO's bioequivalence study
    # report (5.3.1.2) and a regulator's CPP (1.2.7) have no template and
    # never will, because nobody here can author them. Before P18 they were
    # simply absent from the package; the file IS the leaf.
    for document in sorted(uploaded.values(), key=lambda d: d.instance_key):
        manifest.append(
            LeafManifestEntry(
                section=document.instance_key,
                title=_uploaded_leaf_title(document),
                section_number=document.section_number,
                subject_slug=document.subject_slug or None,
                storage_path=document.storage_key,
                md5=document.md5,
                filename=f"{document.instance_key}.pdf",
            )
        )

    return manifest


def _uploaded_leaf_title(document) -> str:
    """The bookmark and table-of-contents title for an uploaded leaf.

    Taken from the target TOC rather than from the uploaded file's name: the
    filename is whatever the CRO called it ("Final_Report_v3_signed.pdf"),
    while the contract knows what the leaf IS. The original filename is
    still stored and shown in the UI, where recognising your own file
    matters more than naming the section.
    """
    leaf = target_leaves_by_number().get(document.section_number)
    title = leaf.title if leaf is not None else document.section_number
    if document.subject_slug:
        return f"{title} — {document.subject_slug}"
    return title
