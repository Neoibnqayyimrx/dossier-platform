"""eCTD sequence builder (P09): orchestrates the ICH backbone
(`app.ectd.index_xml`), EU regional backbone (`app.ectd.regional`),
lifecycle resolution (`app.ectd.lifecycle`), and packaging into one
deterministic, DTD-valid `<sequence-number>/` zip -- the eCTD analog of
P08's `app.ctd.build.build_ctd_package`.

WHY this reuses `assemble_project` wholesale, same as P08: P07 already
refuses to produce anything at all when P06 reports unresolved ERROR
findings (`AssemblyBlockedError`); that exception propagates unchanged, so
this module never re-checks validation itself.

WHY `Sequence` rows are created via the existing P02
`POST /projects/{id}/sequences` endpoint, not auto-created here: that
endpoint already owns "the next sequence number" auto-numbering
(0000, 0001, ...). Duplicating that logic here would give two competing
sources of truth for what the next number is.

WHY each sequence packages as its OWN self-contained zip
(`projects/{id}/ectd/<number>.zip`), not one combined archive: the
reference doc's own physical-structure diagram has every sequence as a
SIBLING directory (`<app>/0000/`, `<app>/0001/`, ...), each independently
addressable -- `modified-file`'s relative `../0000/...` paths are only
meaningful once sequences are extracted next to each other, exactly like
real eCTD submissions are delivered to a gateway one sequence at a time.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assembly.assemble import assemble_project
from app.assembly.pdf import convert_docx_to_pdf
from app.core.storage import StorageClient, get_storage_client
from app.ctd.region_profiles import get_region_profile
from app.ctd.structure import folder_for_section_instance
from app.ectd.backbone import V322BackboneBuilder
from app.ectd.checksum import md5_hex
from app.ectd.leaf import Leaf
from app.ectd.lifecycle import NewLeafInput, PriorLeaf, resolve_lifecycle
from app.ectd.scaffold import scaffold_files
from app.models.project import Project
from app.models.sequence import Sequence
from app.models.sequence_leaf import SequenceLeaf
from app.templating.certificates import render_certificate_placeholder
from app.templating.declarations import render_declaration

ZIP_CONTENT_TYPE = "application/zip"
# Same "idempotent builder" fix as app.ctd.build -- pin the zip's per-entry
# timestamp so byte-identical inputs produce a byte-identical package.
_FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


@dataclass
class EctdBuildResult:
    storage_key: str
    sequence_number: str
    # section_key -> lifecycle operation, for a human-readable build report
    # (mirrors P08's manifest -- "what actually happened in this sequence").
    operations: dict[str, str]


async def _prior_cumulative_state(
    db: AsyncSession, project: Project, sequence: Sequence
) -> tuple[str | None, list[PriorLeaf]]:
    """The most recently built sequence BEFORE `sequence`, and everything
    its cumulative view contained -- `None`/`[]` when `sequence` is the
    project's first (nothing to diff against, everything is `new`)."""
    prior = await db.scalar(
        select(Sequence)
        .where(Sequence.project_id == project.id, Sequence.number < sequence.number)
        .order_by(Sequence.number.desc())
        .limit(1)
    )
    if prior is None:
        return None, []

    rows = (
        await db.scalars(select(SequenceLeaf).where(SequenceLeaf.sequence_id == prior.id))
    ).all()
    return prior.number, [
        PriorLeaf(
            section_key=row.section_key,
            leaf_id=row.leaf_id,
            title=row.title,
            path=row.path,
            checksum=row.checksum,
            operation=row.operation,
            modified_file=row.modified_file,
        )
        for row in rows
    ]


async def build_ectd_sequence(
    db: AsyncSession,
    project: Project,
    sequence: Sequence,
    *,
    overridden_rule_ids: frozenset[str] = frozenset(),
    storage: StorageClient | None = None,
) -> EctdBuildResult:
    storage = storage or get_storage_client()
    profile = get_region_profile(project.region)

    # ---- 1. Gather every candidate leaf for THIS build, keyed by a
    # stable section_key, alongside the physical bytes each one needs if
    # it turns out to be new/replace. -----------------------------------
    ctd_leaves = await assemble_project(
        db, project, overridden_rule_ids=overridden_rule_ids, storage=storage
    )
    module1_by_section = {
        slot.section_number: slot for slot in profile.module1_slots if slot.section_number
    }
    certificate_slot = next((s for s in profile.module1_slots if s.certificate_types), None)
    declaration_slot = next((s for s in profile.module1_slots if s.declaration_types), None)

    new_leaves: list[NewLeafInput] = []
    physical_bytes: dict[str, bytes] = {}

    for leaf in ctd_leaves:
        slot = module1_by_section.get(leaf.section)
        folder = (
            slot.folder
            if slot is not None
            else folder_for_section_instance(leaf.section_number, leaf.subject_slug)
        )
        path = f"{folder}/{leaf.filename}"
        data = storage.get(leaf.storage_path)
        new_leaves.append(
            NewLeafInput(section_key=leaf.section, title=leaf.title, path=path, checksum=leaf.md5)
        )
        physical_bytes[leaf.section] = data

    if certificate_slot is not None:
        for certificate in project.product.certificates:
            if certificate.certificate_type not in certificate_slot.certificate_types:
                continue
            key = f"certificate:{certificate.id}"
            result = render_certificate_placeholder(certificate, storage=storage)
            title = f"{certificate.certificate_type.value} certificate"
            pdf_bytes = convert_docx_to_pdf(storage.get(result.storage_key), bookmark_title=title)
            filename = f"{certificate.certificate_type.value.lower()}-{certificate.id}.pdf"
            path = f"{certificate_slot.folder}/{filename}"
            new_leaves.append(
                NewLeafInput(section_key=key, title=title, path=path, checksum=md5_hex(pdf_bytes))
            )
            physical_bytes[key] = pdf_bytes

    if declaration_slot is not None:
        for declaration in project.declarations:
            if declaration.declaration_type not in declaration_slot.declaration_types:
                continue
            key = f"declaration:{declaration.id}"
            result = render_declaration(declaration, project, storage=storage)
            title = declaration.declaration_type.value.replace("-", " ").title()
            pdf_bytes = convert_docx_to_pdf(storage.get(result.storage_key), bookmark_title=title)
            filename = f"{declaration.declaration_type.value}-{declaration.id}.pdf"
            path = f"{declaration_slot.folder}/{filename}"
            new_leaves.append(
                NewLeafInput(section_key=key, title=title, path=path, checksum=md5_hex(pdf_bytes))
            )
            physical_bytes[key] = pdf_bytes

    # ---- 2. Lifecycle: diff against the prior sequence's cumulative
    # state, decide new/replace/delete, and compute what this sequence's
    # own backbone should (and should NOT) restate. ----------------------
    prior_number, prior_cumulative = await _prior_cumulative_state(db, project, sequence)
    lifecycle = resolve_lifecycle(prior_number, prior_cumulative, new_leaves, sequence.number)

    # Persist the resulting cumulative view as THIS sequence's own
    # SequenceLeaf rows. Idempotent: clear any rows from a previous build
    # attempt of this same sequence first, so re-running a build never
    # accumulates duplicates.
    await db.execute(SequenceLeaf.__table__.delete().where(SequenceLeaf.sequence_id == sequence.id))
    for cum in lifecycle.cumulative_leaves.values():
        db.add(
            SequenceLeaf(
                sequence_id=sequence.id,
                section_key=cum.section_key,
                leaf_id=cum.leaf_id,
                title=cum.title,
                path=cum.path,
                checksum=cum.checksum,
                operation=cum.operation,
                modified_file=cum.modified_file,
            )
        )
    await db.flush()

    # ---- 3. Group this sequence's backbone leaves by Module1Slot for the
    # regional backbone; the ICH backbone gets the full dict as-is (it
    # self-filters to the headings it knows about). ----------------------
    regional_leaves_by_slot: dict[str, list[Leaf]] = {}
    for slot in profile.module1_slots:
        if slot.section_number:
            keys = [slot.section_number] if slot.section_number in lifecycle.backbone_leaves else []
        elif slot.certificate_types:
            keys = [k for k in lifecycle.backbone_leaves if k.startswith("certificate:")]
        elif slot.declaration_types:
            keys = [k for k in lifecycle.backbone_leaves if k.startswith("declaration:")]
        else:
            keys = []
        if keys:
            regional_leaves_by_slot[slot.slot_id] = [lifecycle.backbone_leaves[k] for k in keys]

    related_sequence_numbers = [prior_number] if prior_number else [sequence.number]

    backbone = V322BackboneBuilder().build(
        project,
        sequence.number,
        related_sequence_numbers,
        lifecycle.backbone_leaves,
        regional_leaves_by_slot,
    )

    # ---- 4. Package: utility files + both backbones + only the leaves
    # this sequence actually introduces or changes (an unchanged leaf
    # never appears in `backbone_leaves` at all; a deleted one has no new
    # physical file to add). ---------------------------------------------
    prefix = sequence.number
    files: dict[str, bytes] = {}

    for rel_path, data in scaffold_files("eu").items():
        files[f"{prefix}/{rel_path}"] = data

    files[f"{prefix}/index.xml"] = backbone.index_xml
    files[f"{prefix}/index-md5.txt"] = backbone.index_md5
    files[f"{prefix}/{backbone.regional_xml_relative_path}"] = backbone.regional_xml

    for key, leaf in lifecycle.backbone_leaves.items():
        if leaf.operation not in ("new", "replace"):
            continue
        files[f"{prefix}/{leaf.href}"] = physical_bytes[key]

    zip_bytes = _zip_deterministic(files)
    zip_key = f"projects/{project.id}/ectd/{sequence.number}.zip"
    storage.put(zip_key, zip_bytes, ZIP_CONTENT_TYPE)

    return EctdBuildResult(
        storage_key=zip_key,
        sequence_number=sequence.number,
        operations={k: v.operation for k, v in lifecycle.backbone_leaves.items()},
    )


def _zip_deterministic(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=_FIXED_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, files[path])
    return buffer.getvalue()
