"""CTD package builder (P08): places every P07 leaf PDF and every Module 1
document into the correct NAFDAC folder tree, adds a generated table of
contents, and zips the whole thing with a manifest -- the first genuinely
shippable deliverable (AGENTS.md §2 target #1: a CTD needs no XML backbone
and can go straight to the NAPAMS portal).

WHY this reuses `assemble_project` rather than re-implementing its gate:
P07 already refuses to produce anything at all when P06 reports unresolved
ERROR findings (`AssemblyBlockedError`) -- that exception propagates
unchanged, so this module never re-checks validation itself. AGENTS.md §5
"validation is a gate" only needs to be true in one place.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.assembly.assemble import assemble_project
from app.assembly.pdf import convert_docx_to_pdf
from app.core.storage import StorageClient, get_storage_client
from app.ctd.region_profiles import get_region_profile
from app.ctd.structure import folder_for_section
from app.ctd.toc import build_toc_pdf
from app.models.project import Project
from app.templating.certificates import render_certificate_placeholder
from app.templating.declarations import render_declaration

ZIP_CONTENT_TYPE = "application/zip"

# Zip's own minimum representable date. WHY pin to this rather than "now":
# AGENTS.md §5's "idempotent builders" rule -- same inputs must yield a
# byte-identical package. zipfile stamps each entry with the current
# wall-clock time by default, which would make every build unique -- the
# exact same class of bug P07 found (and fixed) in the PDF /CreationDate,
# caught here by design instead of by a failing byte-identity test.
_FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


@dataclass
class PackagedFile:
    path: str
    md5: str


@dataclass
class CtdBuildResult:
    storage_key: str
    manifest: list[PackagedFile]


async def build_ctd_package(
    db: AsyncSession,
    project: Project,
    *,
    overridden_rule_ids: frozenset[str] = frozenset(),
    storage: StorageClient | None = None,
) -> CtdBuildResult:
    storage = storage or get_storage_client()
    profile = get_region_profile(project.region)

    leaves = await assemble_project(
        db, project, overridden_rule_ids=overridden_rule_ids, storage=storage
    )

    files: dict[str, bytes] = {}
    titles: dict[str, str] = {}

    module1_by_section = {
        slot.section_number: slot for slot in profile.module1_slots if slot.section_number
    }
    for leaf in leaves:
        slot = module1_by_section.get(leaf.section)
        folder = slot.folder if slot is not None else folder_for_section(leaf.section)
        path = f"{folder}/{leaf.filename}"
        files[path] = storage.get(leaf.storage_path)
        titles[path] = leaf.title

    for slot in profile.module1_slots:
        if slot.certificate_types:
            for certificate in project.product.certificates:
                if certificate.certificate_type not in slot.certificate_types:
                    continue
                result = render_certificate_placeholder(certificate, storage=storage)
                title = f"{certificate.certificate_type.value} certificate"
                pdf_bytes = convert_docx_to_pdf(
                    storage.get(result.storage_key), bookmark_title=title
                )
                path = (
                    f"{slot.folder}/"
                    f"{certificate.certificate_type.value.lower()}-{certificate.id}.pdf"
                )
                files[path] = pdf_bytes
                titles[path] = title

        if slot.declaration_types:
            for declaration in project.declarations:
                if declaration.declaration_type not in slot.declaration_types:
                    continue
                result = render_declaration(declaration, project, storage=storage)
                title = declaration.declaration_type.value.replace("-", " ").title()
                pdf_bytes = convert_docx_to_pdf(
                    storage.get(result.storage_key), bookmark_title=title
                )
                path = f"{slot.folder}/{declaration.declaration_type.value}-{declaration.id}.pdf"
                files[path] = pdf_bytes
                titles[path] = title

    files["toc.pdf"] = build_toc_pdf(project, titles)

    # Manifest is computed over real content BEFORE it's added to `files`
    # itself -- a manifest entry for manifest.json would need its own MD5,
    # which doesn't exist until the manifest is already written.
    entries = [
        PackagedFile(path=path, md5=hashlib.md5(data).hexdigest())
        for path, data in sorted(files.items())
    ]
    manifest_json = json.dumps(
        {
            "project_id": str(project.id),
            "region": project.region.value,
            "files": [{"path": e.path, "md5": e.md5} for e in entries],
        },
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    files["manifest.json"] = manifest_json

    zip_bytes = _zip_deterministic(files)
    zip_key = f"projects/{project.id}/ctd-package.zip"
    storage.put(zip_key, zip_bytes, ZIP_CONTENT_TYPE)

    return CtdBuildResult(storage_key=zip_key, manifest=entries)


def _zip_deterministic(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=_FIXED_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, files[path])
    return buffer.getvalue()
