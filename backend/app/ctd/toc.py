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
from docx.oxml import OxmlElement

from app.assembly.pdf import convert_docx_to_pdf
from app.models.project import Project


def build_toc_pdf(project: Project, titles_by_path: dict[str, str]) -> bytes:
    doc = Document()
    doc.add_heading(f"Table of Contents -- {project.product.brand_name}", level=1)

    table = doc.add_table(rows=1, cols=2)
    header_cells = table.rows[0].cells
    header_cells[0].text = "Document"
    header_cells[1].text = "Path"

    _repeat_header_on_every_page(table.rows[0])

    for path in sorted(titles_by_path):
        row = table.add_row()
        _keep_row_on_one_page(row)
        cells = row.cells
        cells[0].text = titles_by_path[path]
        cells[1].text = path

    buffer = io.BytesIO()
    doc.save(buffer)
    return convert_docx_to_pdf(buffer.getvalue(), bookmark_title="Table of Contents")


# WHY these two exist (P17): the TOC became a MULTI-PAGE table the moment
# fourteen not-applicable statement leaves joined the package, and Word's
# default behaviour on a long table is unkind to a reader -- the header row
# appears only on page one, and a row is free to split across the page
# break, leaving a document's title on one page and half its path on the
# next.
#
# Both are ordinary submission-formatting courtesies (a reviewer scanning a
# TOC needs to know which column is which on every page), and both happen to
# have a second payoff: a row split across a page break also interleaves the
# two columns in extracted PDF text, so the path a checker reads back is not
# the path that was written. That is how this surfaced -- as a test
# asserting every placed document is listed, failing on a TOC that listed it
# perfectly well.
#
# Neither setting has a python-docx property, so both are set on the
# underlying WordprocessingML directly.


def _keep_row_on_one_page(row) -> None:
    """`w:cantSplit` -- never break this row across a page boundary."""
    row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def _repeat_header_on_every_page(row) -> None:
    """`w:tblHeader` -- reprint this row at the top of each new page."""
    row._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
