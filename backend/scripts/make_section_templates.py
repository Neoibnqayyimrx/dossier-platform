"""Generate the docxtpl templates that contain loops or generated text.

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

It is idempotent: it overwrites every file it owns from scratch each time.

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


# ---- P19: the data-ready sections ------------------------------------------
#
# All nine are generated here rather than authored in Word, and the reason
# is the one this module opens with: every one of them is a table or a list,
# and a loop is where the mistakes live.


def build_3_2_s_2_1() -> Path:
    """3.2.S.2.1 Name and address of the drug substance manufacturer.

    One document per drug substance, because the answer differs per
    substance -- a combination product may buy its two actives from two
    companies, which is exactly why the eCTD DTD makes `manufacturer` a
    required attribute of each `m3-2-s-drug-substance` element.
    """
    doc = Document()
    doc.add_heading("3.2.S.2.1 Manufacturer", level=1)
    doc.add_paragraph("Drug substance: {{ substance.inn_name }}")
    _looping_table(
        doc,
        ["Item", "Value"],
        ["{{ item.label }}", "{{ item.value }}"],
        loop="item in manufacturer_details",
    )
    note = doc.add_paragraph()
    note.add_run(
        "Each site listed above is responsible for the manufacture of the drug "
        "substance named in this section. GMP evidence for the site is filed in "
        "Module 1."
    ).font.size = Pt(9)
    path = TEMPLATES_DIR / "section_3_2_s_2_1.docx"
    doc.save(path)
    return path


def build_3_2_s_5() -> Path:
    """3.2.S.5 Reference standards or materials, per drug substance."""
    doc = Document()
    doc.add_heading("3.2.S.5 Reference Standards or Materials", level=1)
    doc.add_paragraph("Drug substance: {{ substance.inn_name }}")
    doc.add_paragraph("{{ standard_statement }}")
    note = doc.add_paragraph()
    note.add_run(
        "Reference standards are cited, not reproduced: pharmacopoeial monographs "
        "and their reference substances are copyrighted material (see 3.2.S.4.1)."
    ).font.size = Pt(9)
    path = TEMPLATES_DIR / "section_3_2_s_5.docx"
    doc.save(path)
    return path


def build_3_2_s_6() -> Path:
    """3.2.S.6 Container closure system OF THE DRUG SUBSTANCE.

    Not 3.2.P.7 with different words: this describes how the API is shipped
    and stored between its manufacture and its use in the formulation.
    """
    doc = Document()
    doc.add_heading("3.2.S.6 Container Closure System", level=1)
    doc.add_paragraph("Drug substance: {{ substance.inn_name }}")
    _looping_table(
        doc,
        ["Component", "Description", "Material"],
        ["{{ pack.component.value }}", "{{ pack.description }}", "{{ pack.material or '—' }}"],
        loop="pack in packaging",
    )
    doc.add_paragraph("{{ storage_statement }}")
    path = TEMPLATES_DIR / "section_3_2_s_6.docx"
    doc.save(path)
    return path


def build_3_2_p_3_1() -> Path:
    """3.2.P.3.1 Manufacturer of the DRUG PRODUCT -- one per site."""
    doc = Document()
    doc.add_heading("3.2.P.3.1 Manufacturers", level=1)
    doc.add_paragraph("Site: {{ site.name }}")
    _looping_table(
        doc,
        ["Item", "Value"],
        ["{{ item.label }}", "{{ item.value }}"],
        loop="item in site_details",
    )
    path = TEMPLATES_DIR / "section_3_2_p_3_1.docx"
    doc.save(path)
    return path


def build_3_2_p_3_2() -> Path:
    """3.2.P.3.2 Batch formula -- the same rows as 3.2.P.1's composition
    table, scaled to a batch.

    WHY the batch quantity is COMPUTED here rather than typed: it is
    quantity-per-unit times batch size, an arithmetic a reviewer redoes by
    hand, and rule R04 already reconciles the declared value against it. A
    table where one column is data and the next is prose about that data is
    how the two come to disagree.
    """
    doc = Document()
    doc.add_heading("3.2.P.3.2 Batch Formula", level=1)
    doc.add_paragraph("Product: {{ product.brand_name }}")
    doc.add_paragraph("Batch size: {{ batch_size }}")
    _looping_table(
        doc,
        ["Component", "Standard", "Quantity per unit (mg)", "Quantity per batch (kg)", "Function"],
        [
            "{{ line.component }}",
            "{{ line.spec }}",
            "{{ line.qty_per_unit_mg }}",
            "{{ line.batch_qty_kg }}",
            "{{ line.role }}",
        ],
        loop="line in batch_formula",
    )
    note = doc.add_paragraph()
    note.add_run(
        "Quantities per batch are computed from the quantity per unit and the batch "
        "size; they are not entered independently. The composition of a single unit "
        "is stated in 3.2.P.1."
    ).font.size = Pt(9)
    path = TEMPLATES_DIR / "section_3_2_p_3_2.docx"
    doc.save(path)
    return path


def build_3_2_p_4_5() -> Path:
    """3.2.P.4.5 Excipients of human or animal origin -- the TSE/BSE leaf.

    The two cases are one template because they are one claim with two
    values: either no excipient in the formulation is of human or animal
    origin, or these are, and here is what supports them. The context
    decides which sentence is true; the template never guesses.
    """
    doc = Document()
    doc.add_heading("3.2.P.4.5 Excipients of Human or Animal Origin", level=1)
    doc.add_paragraph("Product: {{ product.brand_name }}")
    doc.add_paragraph("{{ origin_statement }}")
    _looping_table(
        doc,
        ["Excipient", "Function", "Declared origin", "TSE/BSE evidence"],
        [
            "{{ row.name }}",
            "{{ row.function }}",
            "{{ row.origin }}",
            "{{ row.evidence }}",
        ],
        loop="row in excipients_of_concern",
    )
    doc.add_paragraph("{{ undeclared_statement }}")
    path = TEMPLATES_DIR / "section_3_2_p_4_5.docx"
    doc.save(path)
    return path


def build_3_2_p_6() -> Path:
    """3.2.P.6 Reference standards used in finished-product testing."""
    doc = Document()
    doc.add_heading("3.2.P.6 Reference Standards or Materials", level=1)
    doc.add_paragraph("Product: {{ product.brand_name }}")
    _looping_table(
        doc,
        ["Material", "Standard claimed", "Reference standard used"],
        ["{{ row.material }}", "{{ row.claimed }}", "{{ row.standard }}"],
        loop="row in reference_standards",
    )
    path = TEMPLATES_DIR / "section_3_2_p_6.docx"
    doc.save(path)
    return path


def build_3_2_p_7() -> Path:
    """3.2.P.7 Container closure system of the FINISHED PRODUCT, one
    document per pack."""
    doc = Document()
    doc.add_heading("3.2.P.7 Container Closure System", level=1)
    doc.add_paragraph("Product: {{ product.brand_name }}")
    doc.add_paragraph("Pack: {{ pack.component.value }}")
    _looping_table(
        doc,
        ["Item", "Value"],
        ["{{ item.label }}", "{{ item.value }}"],
        loop="item in pack_details",
    )
    doc.add_paragraph("{{ storage_statement }}")
    path = TEMPLATES_DIR / "section_3_2_p_7.docx"
    doc.save(path)
    return path


def build_3_2_r() -> Path:
    """3.2.R Regional information -- whatever THIS region asks for.

    The items come from the region profile, so the same template serves a
    NAFDAC filing and (once its profile is filled in) an EU one.
    """
    doc = Document()
    doc.add_heading("3.2.R Regional Information", level=1)
    doc.add_paragraph("Region: {{ region }}")
    doc.add_paragraph("{{ regional_statement }}")
    _looping_table(
        doc,
        ["Item", "Where it is filed"],
        ["{{ item.title }}", "{{ item.guidance }}"],
        loop="item in regional_information",
    )
    path = TEMPLATES_DIR / "section_3_2_r.docx"
    doc.save(path)
    return path


P19_BUILDERS = (
    build_3_2_s_2_1,
    build_3_2_s_5,
    build_3_2_s_6,
    build_3_2_p_3_1,
    build_3_2_p_3_2,
    build_3_2_p_4_5,
    build_3_2_p_6,
    build_3_2_p_7,
    build_3_2_r,
)


# ---- P20: five templates, eleven sections ----------------------------------
#
# Every builder below is named after a SHAPE, not a section number, and each
# is used by two or three sections. That is the phase's thesis arriving at
# the template layer: a specification is one artifact the CTD asks for of
# three different things, so it is one template that prints its own heading
# and its own owner label from the context.
#
# The heading is `{{ section_number }} {{ section_title }}` rather than a
# literal, which is the mechanism that makes the sharing possible -- and it
# is the same mechanism the fourteen not-applicable statements already share
# one template through (see build_na_statement).


def build_specification() -> Path:
    """3.2.S.4.1, 3.2.P.4.1, 3.2.P.5.1 -- the specification table.

    Replaces P13's `section_3_2_s_4_1.docx`, which was deleted rather than
    left in place: an unreferenced binary template is exactly the thing that
    rots unnoticed, and `git diff` would never show anyone that it had.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("{{ owner_label }}: {{ owner_name }}")
    doc.add_paragraph("Compendial standard: {{ compendial_standard }}")

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

    path = TEMPLATES_DIR / "specification.docx"
    doc.save(path)
    return path


def build_analytical_procedures() -> Path:
    """3.2.S.4.2, 3.2.P.4.2, 3.2.P.5.2 -- hybrid.

    The table is generated from the specification rows (every row already
    carries its method as a citation); the narrative slot describes the
    in-house methods only. A compendial method needs no description here --
    and could not be given one without reproducing copyrighted monograph
    text (AGENTS.md 5).
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    _looping_table(
        doc,
        ["Material", "Test", "Analytical procedure", "Basis"],
        [
            "{{ row.owner }}",
            "{{ row.test_name }}",
            "{{ row.method }}",
            "{{ row.basis }}",
        ],
        loop="row in procedures",
    )
    doc.add_paragraph("{{ in_house_statement }}")
    doc.add_heading("Description of in-house procedures", level=2)
    doc.add_paragraph(
        "{{ narrative.in_house_methods or "
        "'[[AI DRAFT PENDING -- description of in-house analytical procedures]]' }}"
    )
    path = TEMPLATES_DIR / "analytical_procedures.docx"
    doc.save(path)
    return path


def build_justification_of_specification() -> Path:
    """3.2.P.4.4, 3.2.P.5.6 -- hybrid.

    The limits are printed FROM THE SPECIFICATION rows, so the prose is
    read against the actual acceptance criteria rather than against a typed
    restatement of them. A justification defending a limit the
    specification no longer contains is one of the easier ways for a
    dossier to contradict itself.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    _looping_table(
        doc,
        ["Material", "Test", "Acceptance criterion", "Basis"],
        [
            "{{ row.owner }}",
            "{{ row.test_name }}",
            "{{ row.acceptance_criterion }}",
            "{{ row.basis }}",
        ],
        loop="row in limits",
    )
    doc.add_heading("Justification", level=2)
    doc.add_paragraph(
        "{{ narrative.justification or "
        "'[[AI DRAFT PENDING -- justification of the acceptance criteria above]]' }}"
    )
    path = TEMPLATES_DIR / "justification_of_specification.docx"
    doc.save(path)
    return path


def build_batch_analysis() -> Path:
    """3.2.S.4.4, 3.2.P.5.4 -- what the batches actually gave.

    Two tables, and the ORDER of them is the point. First the batches
    themselves (number, date, size, site, purpose), because an assessor's
    first question is which material these numbers describe. Then the
    results, one ROW PER TEST with the acceptance criterion on the same
    line and one cell per batch -- so a limit and every number judged
    against it are read across a single line. A batch-major layout would
    put the limit in a different table from the numbers, which is the
    layout that lets an out-of-specification result pass unnoticed.

    The per-batch result cells use `{%tc %}`, docxtpl's COLUMN loop, for
    the same reason the row loops use `{%tr %}`: the number of batches is
    data, not a fixed template width.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("{{ owner_label }}: {{ owner_name }}")
    doc.add_paragraph("{{ no_batches_statement }}")

    doc.add_heading("Batches", level=2)
    _looping_table(
        doc,
        ["Batch number", "Date of manufacture", "Batch size", "Site", "Purpose"],
        [
            "{{ b.batch_number }}",
            "{{ b.manufacture_date }}",
            "{{ b.batch_size }}",
            "{{ b.site }}",
            "{{ b.purpose }}",
        ],
        loop="b in batches",
    )

    doc.add_heading("Results", level=2)
    # One ROW per test per batch, so the acceptance criterion and the number
    # judged against it are always on the same line -- see
    # quality_control.batch_analysis_context for why this beats the
    # column-per-batch matrix a certificate of analysis uses.
    _looping_table(
        doc,
        ["Test", "Acceptance criterion", "Batch", "Result"],
        [
            "{{ row.test_name }}",
            "{{ row.acceptance_criterion }}",
            "{{ row.batch_number }}",
            "{{ row.result }}",
        ],
        loop="row in results",
    )

    note = doc.add_paragraph()
    note.add_run(
        "Each result is recorded against the specification test it answers, and is "
        "checked against that test's acceptance criterion by rule R22 before export. "
        "The limits printed above are the specification's own -- they are not "
        "re-entered here."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "batch_analysis.docx"
    doc.save(path)
    return path


def build_impurities() -> Path:
    """3.2.S.3.2, 3.2.P.5.5 -- the named impurity profile.

    `Basis of limit` is its own column rather than being folded into the
    limit, because an uncited limit is the query an assessor writes back.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("{{ owner_label }}: {{ owner_name }}")
    doc.add_paragraph("{{ no_impurities_statement }}")
    _looping_table(
        doc,
        ["Impurity", "Type", "Limit", "Basis of limit", "Origin"],
        [
            "{{ row.name }}",
            "{{ row.impurity_type }}",
            "{{ row.limit }}",
            "{{ row.limit_source }}",
            "{{ row.origin }}",
        ],
        loop="row in impurities",
    )
    note = doc.add_paragraph()
    note.add_run(
        "Limits are cited to their source. Where the source is a pharmacopoeial "
        "monograph, the monograph is referenced by name only -- its text is "
        "copyrighted and is never reproduced."
    ).font.size = Pt(9)
    path = TEMPLATES_DIR / "impurities.docx"
    doc.save(path)
    return path


P20_BUILDERS = (
    build_specification,
    build_analytical_procedures,
    build_justification_of_specification,
    build_batch_analysis,
    build_impurities,
)


if __name__ == "__main__":
    built_paths = [build_3_2_s_1(), build_na_statement()]
    built_paths.extend(builder() for builder in P19_BUILDERS)
    built_paths.extend(builder() for builder in P20_BUILDERS)
    for built in built_paths:
        print(f"wrote {built}")
