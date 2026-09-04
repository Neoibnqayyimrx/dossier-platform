"""Generate the 3.2.S drug-substance docxtpl templates.

WHY this script exists (and the earlier templates have no equivalent): the
`.docx` templates are binary artifacts committed to the repo. Every edit to
one is surgery on a zip, and `git diff` shows a reviewer nothing. Templates
written by hand in Word were fine when there were five; they stop being fine
the moment a template needs a loop, because a loop is where the mistakes
live.

So the 3.2.S templates are GENERATED. This script is the source of truth --
readable, diffable, and re-runnable. If a template needs changing, change
the code here and re-run:

    uv run python -m scripts.make_section_templates

It is idempotent: it overwrites both files from scratch every time.

The older templates (cover letter, 1.2, 3.2.P.1, 3.2.P.8.1, 2.3) are
deliberately NOT regenerated here -- they were authored by hand and carry
styling this script does not attempt to reproduce. Converting them would be
a separate, behaviour-preserving change with its own tests.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Pt

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _looping_table(doc, headers: list[str], cells: list[str], loop: str) -> None:
    """A four-row table: bold headers, a row holding `{%tr for ... %}`, the
    data row, and a row holding `{%tr endfor %}`.

    `{%tr %}` is docxtpl's ROW-level loop: the tag is stripped and the rows
    BETWEEN the two tag rows are repeated once per item.

    WHY the tags get rows of their own instead of sharing cells with the
    data: putting `{%tr for %}` and `{%tr endfor %}` in the first and last
    cells of the data row -- which reads like the obvious way to do it --
    makes docxtpl hand Jinja an `endfor` it never sees as row-level, and
    rendering dies with "Encountered unknown tag 'endfor'". The existing
    hand-authored 3.2.P.1 template uses the tag-row form, which works;
    this matches it.
    """
    table = doc.add_table(rows=4, cols=len(headers))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, headers):
        cell.paragraphs[0].add_run(text).bold = True
    table.rows[1].cells[0].text = "{%tr for " + loop + " %}"
    for cell, text in zip(table.rows[2].cells, cells):
        cell.text = text
    table.rows[3].cells[0].text = "{%tr endfor %}"


def build_3_2_s_1() -> Path:
    """3.2.S.1 General Information: nomenclature, structure, properties.

    One document PER DRUG SUBSTANCE -- `substance` is the single active
    ingredient this copy is about, injected by the renderer, not the whole
    product's list.
    """
    doc = Document()
    doc.add_heading("3.2.S.1 General Information", level=1)
    doc.add_paragraph("Drug substance: {{ substance.inn_name }}")

    doc.add_heading("3.2.S.1.1 Nomenclature", level=2)
    _looping_table(
        doc,
        ["Item", "Value"],
        ["{{ item.label }}", "{{ item.value }}"],
        loop="item in nomenclature",
    )

    doc.add_heading("3.2.S.1.2 Structure", level=2)
    doc.add_paragraph("{%p for s in structures %}")
    doc.add_paragraph("Structural formula — {{ s.name }}:")
    doc.add_paragraph("{{ s.image }}")
    doc.add_paragraph("{%p endfor %}")

    doc.add_heading("3.2.S.1.3 General Properties", level=2)
    doc.add_paragraph(
        "{{ narrative.general_properties or "
        "'[[AI DRAFT PENDING -- 3.2.S.1.3 general properties]]' }}"
    )

    path = TEMPLATES_DIR / "section_3_2_s_1.docx"
    doc.save(path)
    return path


def build_3_2_s_4_1() -> Path:
    """3.2.S.4.1 Specification: the table of tests, methods and limits.

    Nothing here is narrative. Every cell is structured data the applicant
    committed to, which is exactly why the free-text field this replaced
    could not produce this page.
    """
    doc = Document()
    doc.add_heading("3.2.S.4.1 Specification", level=1)
    doc.add_paragraph("Drug substance: {{ substance.inn_name }}")
    doc.add_paragraph(
        "Compendial standard: {{ substance.compendial_std.value if "
        "substance.compendial_std else '[[NOT STATED]]' }}"
    )

    _looping_table(
        doc,
        ["Test", "Method", "Acceptance criterion"],
        ["{{ row.test_name }}", "{{ row.method }}", "{{ row.acceptance_criterion }}"],
        loop="row in specification",
    )

    note = doc.add_paragraph()
    note.add_run(
        "Methods are cited, not reproduced. Pharmacopoeial monographs are "
        "copyrighted and are referenced here by name only."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "section_3_2_s_4_1.docx"
    doc.save(path)
    return path


def build_na_statement() -> Path:
    """The not-applicable statement — ONE template for all 14 such leaves.

    WHY one template rather than a template per section: every statement
    says the same three things (which section, that it is not applicable,
    and under which guideline). The only variables are the section number,
    its title, and the citation, all of which arrive in the context. A
    second template would be a second thing to keep in sync for no gain --
    the same "resist a second emit path" reasoning that keeps these leaves
    in the ordinary section registry rather than in a bespoke pipeline.

    WHY the citation is a required-looking, conspicuous field rather than
    optional prose: a statement that a section does not apply is a
    REGULATORY CLAIM. Unsupported, it reads to an assessor as an omission
    with a covering note. Cited, it reads as a scoped dossier. That
    difference is the whole point of the leaf.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)

    doc.add_paragraph("This section is not applicable to the present application.")
    doc.add_paragraph("Basis: {{ citation }}")

    scope = doc.add_paragraph()
    scope.add_run(
        "Submission type: {{ submission_type }}. Applicant: {{ applicant_name }}. "
        "Product: {{ product_name }}."
    ).font.size = Pt(9)

    note = doc.add_paragraph()
    note.add_run(
        "This statement is generated from the applicability rules declared for this "
        "submission type and region. It is filed in place of the section's content so "
        "that the exclusion is explicit rather than inferred from an empty folder."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "na_statement.docx"
    doc.save(path)
    return path


if __name__ == "__main__":
    for built in (build_3_2_s_1(), build_3_2_s_4_1(), build_na_statement()):
        print(f"wrote {built}")
