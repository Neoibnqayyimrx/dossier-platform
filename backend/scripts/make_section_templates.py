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

The older templates (cover letter, 1.2, 3.2.P.1, 2.3) are deliberately
NOT regenerated here -- they were authored by hand and carry styling this
script does not attempt to reproduce. Converting them would be a separate,
behaviour-preserving change with its own tests.

P21 took `stability_summary.docx` (3.2.P.8.1) OFF that list, and not as a
tidy-up: the hand-authored one printed a claimed shelf life beside a
free-text result summary, which is exactly the contradiction the phase
exists to remove. Rewriting it required changing what the page says, so it
came here where the change is diffable.
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


# ---- P21: stability ---------------------------------------------------------


def build_stability_summary() -> Path:
    """3.2.S.7.1, 3.2.P.8.1 -- the summary and conclusion.

    **This replaces the hand-authored template the repo has carried since
    P04**, and the replacement is the point of the phase rather than a
    tidy-up. The old one printed `{{ product.shelf_life_months }}` beside
    `{{ study.result_summary }}`: a claimed period next to a typed
    sentence, with nothing in the document or the code able to tell whether
    either matched the data. It could render "Shelf life: 24 months --
    within specification throughout" over a study that failed dissolution
    at 12.

    Everything numeric on this page now arrives already computed, as
    `claim_statement`, from `app.models.stability.supported_months` -- the
    same function rule R05 checks against. The only free text is the
    conclusion slot, which is the applicant's reading of the data and
    cannot state a period, because the period is printed above it.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("{{ owner_label }}: {{ owner_name }}")
    # NOT "{{ claim_label }}: {{ months }}" -- the sentence is assembled in
    # the context precisely so that the "claimed period exceeds the data"
    # case can render a marker instead of the claim. A template that
    # printed the two fields separately could not make that choice.
    doc.add_paragraph("{{ claim_statement }}")
    doc.add_paragraph("{{ storage_statement }}")

    doc.add_heading("Studies", level=2)
    _looping_table(
        doc,
        ["Study", "Condition", "Batch", "Pack", "Duration (months)", "Timepoints", "Supported"],
        [
            "{{ s.study_type }}",
            "{{ s.condition }}",
            "{{ s.batch_number }}",
            "{{ s.pack }}",
            "{{ s.duration_months }}",
            "{{ s.timepoints }}",
            "{{ s.supported_months }}",
        ],
        loop="s in studies",
    )

    doc.add_heading("Attributes monitored", level=2)
    doc.add_paragraph(
        "{% for test in tests_monitored %}{{ test }}{% if not loop.last %}; "
        "{% endif %}{% endfor %}"
    )

    doc.add_heading("Conclusion", level=2)
    doc.add_paragraph(
        "{{ narrative.conclusion or '[[AI DRAFT PENDING -- stability conclusion]]' }}"
    )
    note = doc.add_paragraph()
    note.add_run(
        "The period stated above is computed from the timepoint results filed in the "
        "corresponding stability data section, judged against the acceptance criteria in "
        "the specification. It is not re-entered here, and this section cannot state a "
        "period the data does not support."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "stability_summary.docx"
    doc.save(path)
    return path


def build_stability_data() -> Path:
    """3.2.S.7.3, 3.2.P.8.3 -- the timepoint tables.

    One BLOCK per study, because a study is the unit an assessor reads:
    this batch, this condition, this pack. Inside each block, one row per
    test per timepoint, with the acceptance criterion and the verdict on
    the same line as the value.

    WHY not the matrix a stability report uses (tests down, timepoints
    across): docxtpl's column loop `{%tc %}` has the same "the tag needs a
    cell of its own" constraint `{%tr %}` has, and nesting a column loop
    inside a row loop inside a document-level `{%p for %}` compounds it --
    P20's build log records that failure mode dying with "Encountered
    unknown tag 'endfor'". The flat form is also the better document: a
    limit printed in one table and the numbers judged against it in another
    is the layout that lets an out-of-specification result pass unnoticed.

    `{%p %}` is docxtpl's PARAGRAPH-level tag: the paragraph holding it is
    removed and what lies between the tags repeats. It is what lets a loop
    span headings and whole tables rather than rows of one table.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("{{ owner_label }}: {{ owner_name }}")
    doc.add_paragraph("{{ no_studies_statement }}")

    doc.add_paragraph("{%p for study in studies %}")
    doc.add_heading(
        "{{ study.study_type }} - {{ study.condition }} - batch {{ study.batch_number }}",
        level=2,
    )
    doc.add_paragraph("Pack: {{ study.pack }}")
    doc.add_paragraph("Protocol: {{ study.protocol }}")
    doc.add_paragraph("{{ study.no_results_statement }}")
    _looping_table(
        doc,
        ["Test", "Acceptance criterion", "Timepoint (months)", "Result", "Against the limit"],
        [
            "{{ row.test_name }}",
            "{{ row.acceptance_criterion }}",
            "{{ row.timepoint_months }}",
            "{{ row.result }}",
            "{{ row.verdict }}",
        ],
        loop="row in study.rows",
    )
    doc.add_paragraph("{%p endfor %}")

    note = doc.add_paragraph()
    note.add_run(
        "Each result is recorded against the specification test it answers, and the "
        "limits printed above are the specification's own -- they are not re-entered "
        "here. A result inside the claimed shelf life that does not meet its criterion "
        'blocks the export (rule R23). "Not checked mechanically" means exactly that: '
        "it is not a pass."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "stability_data.docx"
    doc.save(path)
    return path


def build_stability_commitment() -> Path:
    """3.2.S.7.2, 3.2.P.8.2 -- the post-approval protocol and commitment.

    The section exists because the studies filed with an application are
    usually incomplete -- twelve months of data behind a twenty-four month
    claim is the ordinary case -- and the applicant undertakes to finish
    them, to put the first production batches on stability, and to report
    any out-of-specification result to the agency.

    Hybrid, and the split is the same as the summary's: the protocol table
    is read from the studies themselves, so a commitment cannot name
    batches or timepoints the stability section does not contain, and the
    narrative carries the undertaking's own wording -- which is a legal
    statement the applicant makes, not a number the platform can derive.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("{{ owner_label }}: {{ owner_name }}")
    doc.add_paragraph("{{ claim_label }} claimed: {{ claim_months }} months")
    doc.add_paragraph("{{ no_studies_statement }}")

    doc.add_heading("Post-approval stability protocol", level=2)
    _looping_table(
        doc,
        ["Batch", "Condition", "Pack", "Tested to (months)", "To be continued"],
        [
            "{{ row.batch_number }}",
            "{{ row.condition }}",
            "{{ row.pack }}",
            "{{ row.tested_to_months }}",
            "{{ row.remaining }}",
        ],
        loop="row in protocol",
    )

    doc.add_heading("Stability commitment", level=2)
    doc.add_paragraph(
        "{{ narrative.commitment or '[[AI DRAFT PENDING -- stability commitment]]' }}"
    )
    note = doc.add_paragraph()
    note.add_run(
        "The batches and timepoints above are read from the stability studies filed in "
        "this dossier. They are not a separate list, so this protocol cannot commit to "
        "continuing a study the dossier does not contain."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "stability_commitment.docx"
    doc.save(path)
    return path


# ---------------------------------------------------------------------------
# P22 -- the bioequivalence documents.
# ---------------------------------------------------------------------------


def build_bti_form() -> Path:
    """1.4.1 -- the Bioequivalence Trial Information form.

    A MODULE 1 document with no prose in it at all, built entirely from
    MODULE 5 numbers. That sentence is the whole argument for this
    platform's premise, and this template is where it is cashed: there is
    not one narrative placeholder anywhere below, and the acceptance window
    printed against every interval is read from region config, not typed.

    NAFDAC (like WHO's model form) asks for the study's identity, the
    comparator's identity and batch, the test batch, and the confidence
    intervals -- so the form is a details table plus a results table, once
    per study. The `{%p %}` loop lets one study's block span both.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("Product: {{ product_name }} ({{ generic_name }})")
    doc.add_paragraph("Strength: {{ strength }}    Dosage form: {{ dosage_form }}")
    doc.add_paragraph("Applicant: {{ applicant_name }}")
    doc.add_paragraph("Acceptance window applied: {{ acceptance_window }}")
    doc.add_paragraph("{{ no_studies_statement }}")

    doc.add_paragraph("{%p for study in studies %}")
    doc.add_heading("Study {{ study.study_identifier }}", level=2)
    _looping_table(
        doc,
        ["Item", "Value"],
        ["{{ item.label }}", "{{ item.value }}"],
        loop="item in study.details",
    )
    doc.add_heading("Pharmacokinetic results", level=3)
    _looping_table(
        doc,
        [
            "Parameter",
            "Geometric mean ratio (%)",
            "90 % CI lower",
            "90 % CI upper",
            "Intra-subject CV (%)",
            "Against the window",
        ],
        [
            "{{ row.parameter }}",
            "{{ row.geometric_mean_ratio }}",
            "{{ row.ci_lower }}",
            "{{ row.ci_upper }}",
            "{{ row.intra_subject_cv }}",
            "{{ row.verdict }}",
        ],
        loop="row in study.results",
    )
    doc.add_paragraph("Conclusion: {{ study.conclusion }}")
    doc.add_paragraph("{%p endfor %}")

    note = doc.add_paragraph()
    note.add_run(
        "Every figure on this form is read from the bioequivalence study data filed in "
        "Module 5. Nothing on it is re-entered, so this form cannot state an interval "
        "that 5.3.1.2 and 5.2 do not also state. A confidence interval outside the "
        "acceptance window blocks the export (rule R25)."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "bti_form.docx"
    doc.save(path)
    return path


def build_clinical_study_listing() -> Path:
    """5.2 -- the tabular listing of all clinical studies.

    One row per study, and the LOCATION column is what makes it a listing
    rather than a summary: an assessor reads this table to find the report,
    so every row names the leaf its report is filed at.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("Product: {{ product_name }} ({{ generic_name }})")
    doc.add_paragraph("{{ no_studies_statement }}")

    _looping_table(
        doc,
        ["Study", "Type", "Design", "Subjects", "Comparator", "Filed at", "Outcome"],
        [
            "{{ row.study_identifier }}",
            "{{ row.kind }}",
            "{{ row.design }}",
            "{{ row.subjects }}",
            "{{ row.comparator }}",
            "{{ row.location }}",
            "{{ row.outcome }}",
        ],
        loop="row in rows",
    )

    note = doc.add_paragraph()
    note.add_run(
        "This listing is generated by walking the studies actually filed in this "
        "dossier. It is not a separate list, so it cannot name a study that is not "
        "here, and cannot omit one that is."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "clinical_study_listing.docx"
    doc.save(path)
    return path


def build_be_study_summary() -> Path:
    """5.3.1.2 -- the structured summary that accompanies the CRO's report.

    It says so on the page, in the note at the bottom: this document is not
    the study report. Saying that in the document matters, because a leaf
    holding only a two-page summary where an assessor expects a study
    report is a deficiency letter, and the platform must not look like it
    is offering one as a substitute.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("Product: {{ product_name }}    Strength: {{ strength }}")
    doc.add_paragraph("Acceptance window applied: {{ acceptance_window }}")
    doc.add_paragraph("{{ no_studies_statement }}")

    doc.add_paragraph("{%p for study in studies %}")
    doc.add_heading("Study {{ study.study_identifier }} — {{ study.title }}", level=2)
    doc.add_paragraph("Design: {{ study.design }}")
    doc.add_paragraph("Subjects: {{ study.subjects }}")
    doc.add_paragraph(
        "Analyte: {{ study.analyte }} — bioanalytical method: {{ study.bioanalytical_method }}"
    )
    doc.add_paragraph("Conducted by: {{ study.cro_name }}, {{ study.study_site }}")
    doc.add_paragraph(
        "Reference product: {{ study.comparator }}, batch {{ study.comparator_batch }}, "
        "expiry {{ study.comparator_expiry }}"
    )
    doc.add_paragraph(
        "Test product: batch {{ study.test_batch }}, batch size {{ study.test_batch_size }}"
    )
    _looping_table(
        doc,
        [
            "Parameter",
            "Geometric mean ratio (%)",
            "90 % CI lower",
            "90 % CI upper",
            "Against the window",
        ],
        [
            "{{ row.parameter }}",
            "{{ row.geometric_mean_ratio }}",
            "{{ row.ci_lower }}",
            "{{ row.ci_upper }}",
            "{{ row.verdict }}",
        ],
        loop="row in study.results",
    )
    doc.add_paragraph("{{ study.conclusion }}")
    doc.add_paragraph("{%p endfor %}")

    note = doc.add_paragraph()
    note.add_run(
        "This is a structured summary generated from the bioequivalence study data on "
        "file. It accompanies, and does not replace, the full study report filed at "
        "this same leaf."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "be_study_summary.docx"
    doc.save(path)
    return path


def build_biowaiver_request() -> Path:
    """1.2.17 and 1.2.18 -- one template, two leaves.

    The same call `specification.docx` makes for its three owners: a
    biowaiver request is one document shape asked of two different
    arguments. What differs between them is the BASIS, which is data
    (app/templating/bioequivalence.py), not layout -- so two templates
    would be two places for one page to drift.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("Product: {{ product_name }} ({{ generic_name }})")
    doc.add_paragraph("Dosage form: {{ dosage_form }}")
    doc.add_paragraph("{{ no_requests_statement }}")

    doc.add_paragraph("{%p for request in requests %}")
    doc.add_heading("Request for {{ request.strength }}", level=2)
    doc.add_paragraph("Basis: {{ request.basis }}")
    _looping_table(
        doc,
        ["Item", "Value"],
        ["{{ item.label }}", "{{ item.value }}"],
        loop="item in request.details",
    )
    doc.add_paragraph("{%p endfor %}")

    doc.add_heading("Justification", level=2)
    doc.add_paragraph(
        "{{ narrative.justification or '[[AI DRAFT PENDING -- biowaiver justification]]' }}"
    )

    note = doc.add_paragraph()
    note.add_run(
        "A biowaiver and an in vivo bioequivalence study are alternatives, not "
        "companions: exactly one route must be filed for a given strength, and rule "
        "R06 blocks the export when both or neither are present."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "biowaiver_request.docx"
    doc.save(path)
    return path


def build_smpc() -> Path:
    """1.3.1 -- the Summary of Product Characteristics.

    The section numbers on the page are the SmPC's own (1, 2, 3, 4.1, ...
    6.6), not the CTD's, and that is not decoration: an assessor's query
    arrives as "section 6.4 contradicts 3.2.P.8", and a document that does
    not carry those numbers cannot be answered against.

    Read the 6.x block against the 4.x block above it. Sections 6.1, 6.3,
    6.4 and 6.5 bind `shared.*` -- values computed once for all three
    documents. Sections 4.1 to 4.9 bind authored fields. Sections 5.1 to
    5.3 are the only narrative placeholders in the file. That layout IS the
    phase: derived, authored and drafted are visibly three different kinds
    of content, in one document, and a reader can see which is which.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)

    doc.add_heading("1. Name of the medicinal product", level=2)
    doc.add_paragraph("{{ shared.product_name }}")

    doc.add_heading("2. Qualitative and quantitative composition", level=2)
    doc.add_paragraph("{{ shared.strength }}")
    doc.add_paragraph("For the full list of excipients, see section 6.1.")

    doc.add_heading("3. Pharmaceutical form", level=2)
    doc.add_paragraph("{{ shared.dosage_form }}")

    doc.add_heading("4. Clinical particulars", level=2)
    doc.add_heading("4.1 Therapeutic indications", level=3)
    doc.add_paragraph("{{ therapeutic_indications }}")
    doc.add_heading("4.2 Posology and method of administration", level=3)
    doc.add_paragraph("{{ posology_and_administration }}")
    doc.add_paragraph("Route of administration: {{ shared.route_of_administration }}")

    doc.add_heading("4.3 Contraindications", level=3)
    # A LIST, printed from the structured entries rather than from a
    # paragraph, because the leaflet prints the same entries and rule R32
    # has to be able to name the one the leaflet dropped.
    doc.add_paragraph("{%p for item in contraindications %}")
    doc.add_paragraph("{{ item }}", style="List Bullet")
    doc.add_paragraph("{%p endfor %}")

    doc.add_heading("4.4 Special warnings and precautions for use", level=3)
    doc.add_paragraph("{%p for item in special_warnings %}")
    doc.add_paragraph("{{ item }}", style="List Bullet")
    doc.add_paragraph("{%p endfor %}")

    doc.add_heading("4.5 Interaction with other medicinal products", level=3)
    doc.add_paragraph("{{ interactions }}")
    doc.add_heading("4.6 Fertility, pregnancy and lactation", level=3)
    doc.add_paragraph("{{ pregnancy_and_lactation }}")
    doc.add_heading("4.7 Effects on ability to drive and use machines", level=3)
    doc.add_paragraph("{{ effects_on_driving }}")

    doc.add_heading("4.8 Undesirable effects", level=3)
    _looping_table(
        doc,
        ["Undesirable effect", "Frequency"],
        ["{{ row.effect }}", "{{ row.frequency }}"],
        loop="row in undesirable_effects",
    )

    doc.add_heading("4.9 Overdose", level=3)
    doc.add_paragraph("{{ overdose }}")

    doc.add_heading("5. Pharmacological properties", level=2)
    doc.add_heading("5.1 Pharmacodynamic properties", level=3)
    doc.add_paragraph(
        "{{ narrative.pharmacodynamic_properties or "
        "'[[AI DRAFT PENDING -- pharmacodynamic properties]]' }}"
    )
    doc.add_heading("5.2 Pharmacokinetic properties", level=3)
    doc.add_paragraph(
        "{{ narrative.pharmacokinetic_properties or "
        "'[[AI DRAFT PENDING -- pharmacokinetic properties]]' }}"
    )
    doc.add_heading("5.3 Preclinical safety data", level=3)
    doc.add_paragraph(
        "{{ narrative.preclinical_safety or '[[AI DRAFT PENDING -- preclinical safety]]' }}"
    )

    doc.add_heading("6. Pharmaceutical particulars", level=2)
    doc.add_heading("6.1 List of excipients", level=3)
    doc.add_paragraph("{{ shared.excipients }}")
    doc.add_heading("6.2 Incompatibilities", level=3)
    doc.add_paragraph("{{ incompatibilities }}")
    doc.add_heading("6.3 Shelf life", level=3)
    doc.add_paragraph("{{ shared.shelf_life }}")
    doc.add_heading("6.4 Special precautions for storage", level=3)
    doc.add_paragraph("{{ shared.storage_condition }}")
    doc.add_heading("6.5 Nature and contents of container", level=3)
    doc.add_paragraph("{{ shared.container }}")
    doc.add_heading("6.6 Special precautions for disposal", level=3)
    doc.add_paragraph("{{ disposal }}")

    doc.add_heading("7. Marketing authorisation holder", level=2)
    doc.add_paragraph("{{ marketing_authorisation_holder }}")
    doc.add_paragraph("{{ marketing_authorisation_holder_address }}")
    doc.add_paragraph("Manufactured by: {{ manufacturer_name }}")

    note = doc.add_paragraph()
    note.add_run(
        "Sections 6.1, 6.3, 6.4 and 6.5 are computed from the product data, the "
        "packaging rows filed at 3.2.P.7 and the stability data filed at 3.2.P.8. "
        "They are the same values printed on the label (1.3.2) and in the leaflet "
        "(1.3.3), read from one place -- so the three documents cannot state "
        "different shelf lives, storage conditions or pack sizes."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "smpc.docx"
    doc.save(path)
    return path


def build_labelling() -> Path:
    """1.3.2 -- the outer and inner labels.

    Two tables from one dataset. The inner label is a SUBSET of the outer
    one, not a second document: an immediate-container label on a blister
    strip has room for four things, and which four is a packaging
    constraint, not a different set of facts. Both tables are built from
    `shared` in app/templating/product_information.py, so a value can only
    be on both or on neither.

    The overprinted fields at the bottom are the phase's one deliberate
    blank. Batch number, manufacturing date and expiry are applied by the
    packing line for each batch; a dossier that filled them in would file
    one batch's label as the artwork for every batch. Naming them as
    overprinted is what an assessor reviewing artwork expects to see.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)

    doc.add_heading("Outer label (carton)", level=2)
    _looping_table(
        doc,
        ["Item", "Text on the label"],
        ["{{ row.label }}", "{{ row.value }}"],
        loop="row in outer_label_rows",
    )

    doc.add_heading("Inner label (immediate container)", level=2)
    doc.add_paragraph(
        "The immediate container carries the minimum set below. Every value is the "
        "same value printed on the carton above."
    )
    _looping_table(
        doc,
        ["Item", "Text on the label"],
        ["{{ row.label }}", "{{ row.value }}"],
        loop="row in inner_label_rows",
    )

    doc.add_heading("Applied at packing (overprinted)", level=2)
    doc.add_paragraph("{%p for item in overprinted_fields %}")
    doc.add_paragraph("{{ item }}", style="List Bullet")
    doc.add_paragraph("{%p endfor %}")

    note = doc.add_paragraph()
    note.add_run(
        "This label is generated in full from the product data -- there is no drafted "
        "text on it at all. Every value it carries is the value printed in the SmPC "
        "(1.3.1) and the patient leaflet (1.3.3), because all three read one dataset."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "labelling.docx"
    doc.save(path)
    return path


def build_patient_information_leaflet() -> Path:
    """1.3.3 -- the patient information leaflet.

    The six numbered headings are the leaflet's statutory ones, in their
    statutory order, and they are phrased as a patient reads them ("What X
    is used for", not "Therapeutic indications").

    Each narrative slot is followed by the STRUCTURED list it paraphrases,
    and both are on the page on purpose. The prose is what makes the
    leaflet readable; the list is what makes it complete. A paraphrase can
    silently drop a contraindication, and rule R32 checks that it did not --
    but the list means the leaflet carries the contraindication even when
    the prose is still a draft.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("{{ shared.product_name }}")
    doc.add_paragraph(
        "Read all of this leaflet carefully before you start taking this medicine, "
        "because it contains important information for you."
    )

    doc.add_heading("1. What this medicine is and what it is used for", level=2)
    doc.add_paragraph(
        "{{ narrative.what_it_is_used_for or "
        "'[[AI DRAFT PENDING -- what this medicine is used for]]' }}"
    )
    doc.add_paragraph("Active ingredient(s): {{ shared.strength }}")

    doc.add_heading("2. What you need to know before you take this medicine", level=2)
    doc.add_paragraph(
        "{{ narrative.before_you_take_it or "
        "'[[AI DRAFT PENDING -- before you take this medicine]]' }}"
    )
    doc.add_paragraph("Do not take this medicine if any of the following apply to you:")
    doc.add_paragraph("{%p for item in contraindications %}")
    doc.add_paragraph("{{ item }}", style="List Bullet")
    doc.add_paragraph("{%p endfor %}")
    doc.add_paragraph("Talk to your doctor or pharmacist before taking this medicine if:")
    doc.add_paragraph("{%p for item in special_warnings %}")
    doc.add_paragraph("{{ item }}", style="List Bullet")
    doc.add_paragraph("{%p endfor %}")

    doc.add_heading("3. How to take this medicine", level=2)
    doc.add_paragraph(
        "{{ narrative.how_to_take_it or '[[AI DRAFT PENDING -- how to take this medicine]]' }}"
    )
    doc.add_paragraph("How it is taken: {{ shared.route_of_administration }}")

    doc.add_heading("4. Possible side effects", level=2)
    doc.add_paragraph(
        "{{ narrative.possible_side_effects or "
        "'[[AI DRAFT PENDING -- possible side effects]]' }}"
    )
    _looping_table(
        doc,
        ["Side effect", "How often it happens"],
        ["{{ row.effect }}", "{{ row.frequency }}"],
        loop="row in undesirable_effects",
    )

    doc.add_heading("5. How to store this medicine", level=2)
    doc.add_paragraph("{{ shared.storage_condition }}")
    doc.add_paragraph("Do not use this medicine after the expiry date printed on the pack.")
    doc.add_paragraph("Shelf life: {{ shared.shelf_life }}")
    doc.add_paragraph("{{ disposal }}")

    doc.add_heading("6. What this medicine contains, and other information", level=2)
    doc.add_paragraph("The other ingredients are: {{ shared.excipients }}")
    doc.add_paragraph("What the pack contains: {{ shared.container }}")
    doc.add_paragraph("Marketing authorisation holder: {{ marketing_authorisation_holder }}")
    doc.add_paragraph("{{ marketing_authorisation_holder_address }}")
    doc.add_paragraph("Manufactured by: {{ manufacturer_name }}")

    note = doc.add_paragraph()
    note.add_run(
        "The storage, shelf life, pack and ingredient statements above are the same "
        "values printed in the SmPC (1.3.1) and on the label (1.3.2). The drafted "
        "sections are written in a patient register and are checked for plain "
        "language before export (rule R33); the bulleted lists come straight from the "
        "SmPC's own sections 4.3 and 4.4, so the leaflet cannot omit a "
        "contraindication the SmPC states."
    ).font.size = Pt(9)

    path = TEMPLATES_DIR / "patient_information_leaflet.docx"
    doc.save(path)
    return path


P23_BUILDERS = (
    build_smpc,
    build_labelling,
    build_patient_information_leaflet,
)


P22_BUILDERS = (
    build_bti_form,
    build_clinical_study_listing,
    build_be_study_summary,
    build_biowaiver_request,
)


P21_BUILDERS = (
    build_stability_summary,
    build_stability_data,
    build_stability_commitment,
)


P20_BUILDERS = (
    build_specification,
    build_analytical_procedures,
    build_justification_of_specification,
    build_batch_analysis,
    build_impurities,
)


# ---- P24: the derived documents --------------------------------------------


def build_qis() -> Path:
    """1.4.2 -- the Quality Information Summary.

    Every value block prints the SOURCE beside the value. That column is
    the document's most important feature and the cheapest: it turns the
    form from "a set of claims about the product" into "a set of pointers
    into Module 3", which is what an assessor actually wants from a
    summary. It also makes a wrong value traceable in one step instead of
    a search.

    No narrative placeholder appears anywhere below, and that is checked --
    the registry gives 1.4.2 no slots, for the same reason 1.4.1 has none.
    """
    doc = Document()
    doc.add_heading("{{ section_number }} {{ section_title }}", level=1)
    doc.add_paragraph("Product: {{ product_name }}")

    doc.add_heading("Part 1 — General information", level=2)
    _looping_table(
        doc,
        ["Item", "Value", "Source"],
        ["{{ item.label }}", "{{ item.value }}", "{{ item.source }}"],
        loop="item in general",
    )

    doc.add_heading("Part 2 — Drug substance", level=2)
    doc.add_paragraph("{%p for substance in substances %}")
    doc.add_heading("{{ substance.name }}", level=3)
    doc.add_paragraph("Identity and general properties")
    _looping_table(
        doc,
        ["Item", "Value", "Source"],
        ["{{ item.label }}", "{{ item.value }}", "{{ item.source }}"],
        loop="item in substance.identity",
    )
    doc.add_paragraph("Specification")
    _looping_table(
        doc,
        ["Test", "Method", "Acceptance criterion"],
        [
            "{{ row.test_name }}",
            "{{ row.method }}",
            "{{ row.acceptance_criterion }}",
        ],
        loop="row in substance.specification",
    )
    doc.add_paragraph("Impurities")
    _looping_table(
        doc,
        ["Impurity", "Type", "Limit", "Basis of the limit"],
        [
            "{{ row.name }}",
            "{{ row.impurity_type }}",
            "{{ row.limit }}",
            "{{ row.limit_source }}",
        ],
        loop="row in substance.impurities",
    )
    doc.add_paragraph("Stability")
    _looping_table(
        doc,
        ["Item", "Value", "Source"],
        ["{{ item.label }}", "{{ item.value }}", "{{ item.source }}"],
        loop="item in substance.stability",
    )
    doc.add_paragraph("{%p endfor %}")

    doc.add_heading("Part 3 — Drug product", level=2)

    doc.add_paragraph("Composition (per batch)")
    _looping_table(
        doc,
        ["Component", "Specification", "Quantity per unit (mg)", "Quantity per batch (kg)"],
        [
            "{{ row.component }}",
            "{{ row.spec }}",
            "{{ row.qty_per_unit_mg }}",
            "{{ row.batch_qty_kg }}",
        ],
        loop="row in composition",
    )

    doc.add_paragraph("Finished product specification")
    _looping_table(
        doc,
        ["Test", "Method", "Acceptance criterion"],
        [
            "{{ row.test_name }}",
            "{{ row.method }}",
            "{{ row.acceptance_criterion }}",
        ],
        loop="row in product_specification",
    )

    doc.add_paragraph("Batches filed")
    _looping_table(
        doc,
        ["Batch", "Date", "Size", "Site", "Purpose"],
        [
            "{{ row.batch_number }}",
            "{{ row.manufacture_date }}",
            "{{ row.batch_size }}",
            "{{ row.site }}",
            "{{ row.purpose }}",
        ],
        loop="row in batches",
    )

    doc.add_paragraph("Container closure system")
    _looping_table(
        doc,
        ["Component", "Description", "Source"],
        ["{{ item.label }}", "{{ item.value }}", "{{ item.source }}"],
        loop="item in container",
    )

    doc.add_paragraph("Stability and shelf life")
    _looping_table(
        doc,
        ["Item", "Value", "Source"],
        ["{{ item.label }}", "{{ item.value }}", "{{ item.source }}"],
        loop="item in product_stability",
    )

    note = doc.add_paragraph()
    note.add_run("{{ derivation_note }}").font.size = Pt(9)

    path = TEMPLATES_DIR / "qis.docx"
    doc.save(path)
    return path


P24_BUILDERS = (build_qis,)


if __name__ == "__main__":
    built_paths = [build_3_2_s_1(), build_na_statement()]
    built_paths.extend(builder() for builder in P19_BUILDERS)
    built_paths.extend(builder() for builder in P20_BUILDERS)
    built_paths.extend(builder() for builder in P21_BUILDERS)
    built_paths.extend(builder() for builder in P22_BUILDERS)
    built_paths.extend(builder() for builder in P23_BUILDERS)
    built_paths.extend(builder() for builder in P24_BUILDERS)
    for built in built_paths:
        print(f"wrote {built}")
