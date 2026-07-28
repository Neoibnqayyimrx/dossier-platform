"""Table of contents builder (P08): a generated, bookmarked, searchable PDF
listing every document actually placed in the package -- title and
package-relative path -- so it can never drift from what's really in the
ZIP (it's built from the exact same path/title dict `build.py` just
assembled, not a separate query).

WHY plain python-docx, not docxtpl: same reasoning as certificates.py/
declarations.py -- a table of (title, path) pairs built directly from
Python has no pre-authored template to fill.
"""

from __future__ import annotations

import io

from docx import Document

from app.assembly.pdf import convert_docx_to_pdf
from app.models.project import Project


def build_toc_pdf(project: Project, titles_by_path: dict[str, str]) -> bytes:
    doc = Document()
    doc.add_heading(f"Table of Contents -- {project.product.brand_name}", level=1)

    table = doc.add_table(rows=1, cols=2)
    header_cells = table.rows[0].cells
    header_cells[0].text = "Document"
    header_cells[1].text = "Path"

    for path in sorted(titles_by_path):
        cells = table.add_row().cells
        cells[0].text = titles_by_path[path]
        cells[1].text = path

    buffer = io.BytesIO()
    doc.save(buffer)
    return convert_docx_to_pdf(buffer.getvalue(), bookmark_title="Table of Contents")
