"""Table of contents builder (P08, extended in P24): generated, bookmarked,
searchable PDFs listing the documents actually placed in the package --
title and package-relative path -- so they can never drift from what's
really in the ZIP (they are built from the exact same path/title dict
`build.py` just assembled, not a separate query).

Two shapes, one function underneath:

  * `build_toc_pdf` -- the whole-package TOC at `toc.pdf` (P08).
  * `build_module_toc_pdf` -- leaves 1.1, 2.1, 3.1 and 5.1, one per module
    (P24). These are real leaves in the target TOC, not conveniences: a
    NAFDAC CTD has no XML backbone, so the per-module TOC is the ONLY
    navigation an assessor gets, and the source dossier files one per
    module.

WHY these are built here rather than registered as ordinary sections:
`render_section` is handed a Project and asked for a document. A table of
contents cannot be produced from a Project -- it is a function of the
PACKAGE, which does not exist until every other leaf has been rendered and
placed. Registering 1.1 would mean writing a TOC from the section registry
instead of from the tree, and the two can disagree the moment a leaf is
conditionally emitted (a biowaiver request, a not-applicable statement, an
uploaded file that never arrived). Deriving it from the placed files makes
disagreement unrepresentable.

WHY there is no per-module TOC in the eCTD package: in eCTD the XML
backbone IS the table of contents -- an agency's software renders the tree
from `index.xml`, and a second, static list of the same leaves is one more
thing that can go stale. The paper-style TOC exists precisely because the
NAFDAC/NAPAMS CTD has no backbone to render.

WHY plain python-docx, not docxtpl: same reasoning as certificates.py/
declarations.py -- a table of (title, path) pairs built directly from
Python has no pre-authored template to fill.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

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


# ---- P24: the per-module tables of contents (leaves 1.1, 2.1, 3.1, 5.1) ----
#
# WHY a declared table rather than "one per module that has files": Module 4
# has files (its not-applicable statement) and owes NO table of contents --
# the source dossier files a single page saying the module does not apply,
# and a one-line TOC in front of it would be a navigation aid for nothing.
# Which modules owe a TOC is a regulatory fact from the target contract, so
# it is written down rather than inferred from the tree.
#
# `scripts/check_target_toc.py` imports this map to decide whether a `toc`
# leaf is producible, for the same single-source reason `folder_for_section`
# is the only answer to "where does this go": a second list of TOC leaf
# numbers in the check would be a list that can disagree with the builder.


@dataclass(frozen=True)
class ModuleTocLeaf:
    """One per-module table of contents, as a leaf in its own right."""

    number: str
    module: int
    title: str
    folder: str

    @property
    def filename(self) -> str:
        return f"{self.number}.pdf"

    @property
    def path(self) -> str:
        return f"{self.folder}/{self.filename}"

    @property
    def package_prefix(self) -> str:
        """The path prefix of everything this TOC lists.

        The module folders are named `m1/`, `m2/` ... by `app.ctd.structure`
        and the region profiles, so the module number IS the prefix. Reading
        it off `module` rather than storing a fourth field keeps the two from
        drifting: a TOC that listed the wrong module's leaves would still
        render perfectly and be wrong on every line.
        """
        return f"m{self.module}/"


MODULE_TOC_LEAVES: dict[str, ModuleTocLeaf] = {
    "1.1": ModuleTocLeaf(
        number="1.1",
        module=1,
        title="Table of Contents of Module 1",
        folder="m1/11-table-of-contents",
    ),
    "2.1": ModuleTocLeaf(
        number="2.1",
        module=2,
        title="Table of Contents of Module 2",
        folder="m2/21-table-of-contents",
    ),
    "3.1": ModuleTocLeaf(
        number="3.1",
        module=3,
        title="Table of Contents of Module 3",
        folder="m3/31-table-of-contents",
    ),
    "5.1": ModuleTocLeaf(
        number="5.1",
        module=5,
        title="Table of Contents of Module 5",
        folder="m5/51-table-of-contents",
    ),
}


def build_module_toc_pdf(
    project: Project, leaf: ModuleTocLeaf, titles_by_path: dict[str, str]
) -> bytes:
    """The table of contents for one module, from the leaves actually placed.

    `titles_by_path` is the whole package; this filters it to the module.
    Filtering here rather than asking the caller for a pre-filtered dict is
    deliberate -- the caller would have to know how module folders are named,
    which is exactly the fact `package_prefix` keeps in one place.

    Not-applicable statements are listed like any other leaf, and that is a
    requirement rather than a side effect (P24a task 2): an assessor opening
    Module 2's TOC expects to see 2.4-2.7 accounted for. A TOC that silently
    omitted them would read as an incomplete module rather than a scoped one
    -- the same failure the statements themselves exist to prevent,
    reintroduced one level up.
    """
    paths = sorted(path for path in titles_by_path if path.startswith(leaf.package_prefix))

    doc = Document()
    doc.add_heading(f"{leaf.number} {leaf.title}", level=1)
    doc.add_paragraph(f"{project.product.brand_name} — {project.region.value}")

    if not paths:
        # A module with no leaves is a real state (an all-uploaded Module 5
        # before any report is attached), and a blank page under a heading
        # is indistinguishable from a build that failed. Say which it is.
        doc.add_paragraph(
            f"No documents are currently placed in Module {leaf.module} of this package."
        )
    else:
        table = doc.add_table(rows=1, cols=2)
        header_cells = table.rows[0].cells
        header_cells[0].text = "Document"
        header_cells[1].text = "Path"
        _repeat_header_on_every_page(table.rows[0])

        for path in paths:
            row = table.add_row()
            _keep_row_on_one_page(row)
            cells = row.cells
            cells[0].text = titles_by_path[path]
            cells[1].text = path

    buffer = io.BytesIO()
    doc.save(buffer)
    return convert_docx_to_pdf(buffer.getvalue(), bookmark_title=leaf.title)
