"""The documents that are derived from other documents (P24b, P24c).

The Quality Information Summary (1.4.2) and the Quality Overall Summary
(2.3) restate Module 3 in two other layouts. In a hand-built dossier that
restatement is retyping, and retyping is where dossiers acquire the
contradictions an assessor finds: a limit tightened in 3.2.P.5.1 that the
QIS still reports at last year's value, a shelf life extended in 3.2.P.8.1
that the QOS does not follow.

**These tests are the phase's actual deliverable.** The templates and the
context builders are just code; the claim being made is that divergence is
now unrepresentable, and a claim like that is only worth as much as the
test that tries to break it.

The strategy is mutation. Build a project, render the derived document,
then CHANGE A FACT IN MODULE 3 and render again. If the derived value
follows, it was read from Module 3. If it does not, the document has its
own copy of that fact -- which is the defect, whatever the code looks
like.
"""

from __future__ import annotations

from app.seed.ampiclox import build_ampiclox
from app.seed.examox import build_examox
from app.templating.context import build_context
from app.templating.derived import section_contexts
from app.templating.qis import qis_context
from app.templating.registry import get_section


def _qis(project) -> dict:
    return qis_context(get_section("1.4.2"), project)


def _values(sourced) -> dict[str, str]:
    """A list of SourcedValue as {label: value}, for readable assertions."""
    return {item.label: item.value for item in sourced}


# ---- P24b: the QIS cannot diverge from Module 3 -----------------------------


def test_qis_shelf_life_follows_module_3():
    """The single most consequential field on the form.

    A QIS is the first thing an assessor reads. A shelf life stated there
    and contradicted in 3.2.P.8.1 is a contradiction acted upon before it
    is noticed.
    """
    project = build_examox(buggy=False)

    before = _values(_qis(project)["product_stability"])["Shelf life"]

    project.product.shelf_life_months = 12
    after = _values(_qis(project)["product_stability"])["Shelf life"]

    assert before != after
    # Not merely "it changed" -- it changed to exactly what 3.2.P.8.1 now
    # says. A field that moved to some other value of its own would pass a
    # bare inequality check and still be a second opinion.
    module3 = build_context("3.2.P.8.1", project)
    assert after == module3["claim_statement"]


def test_qis_cannot_state_a_shelf_life_module_3_refuses_to_print():
    """The property that makes the derivation worth having.

    3.2.P.8.1 will not print a claimed shelf life the long-term data do not
    reach; it prints a marker naming both figures instead (rule R05 has
    already blocked the export). Because the QIS field IS that string, an
    unsupported claim is unprintable on the form as well. A QIS with its
    own `shelf_life_months` lookup would print the unsupported claim on
    page one.
    """
    project = build_examox(buggy=False)
    project.product.shelf_life_months = 600

    shelf_life = _values(_qis(project)["product_stability"])["Shelf life"]

    assert "NOT SUPPORTED" in shelf_life
    assert "600" in shelf_life


def test_qis_specification_is_the_module_3_specification():
    project = build_examox(buggy=False)

    row = project.product.specification[0]
    row.acceptance_criterion = "95.0 % to 105.0 % of the stated amount"

    qis_rows = _qis(project)["product_specification"]
    module3_rows = build_context("3.2.P.5.1", project)["specification"]

    assert qis_rows == module3_rows
    assert any(
        r["acceptance_criterion"] == "95.0 % to 105.0 % of the stated amount" for r in qis_rows
    )


def test_qis_composition_follows_the_batch_formula():
    """Including the arithmetic, not just the typed numbers.

    `batch_qty_kg` is COMPUTED in 3.2.P.3.2 from quantity per unit and
    batch size, never read from the filer's declared figure. Halving the
    per-unit quantity must halve it on the QIS too -- which it can only do
    if the form is printing the computation rather than a stored result.
    """
    project = build_examox(buggy=False)
    line = project.product.batch_formula[0]

    before = {row["component"]: row["batch_qty_kg"] for row in _qis(project)["composition"]}
    line.qty_per_unit_mg = line.qty_per_unit_mg / 2
    after = {row["component"]: row["batch_qty_kg"] for row in _qis(project)["composition"]}

    assert after[line.component] == before[line.component] / 2


def test_qis_substance_blocks_are_per_active_not_per_product():
    """A fixed-dose combination owes a QIS block per active.

    AMPICLOX is ampicillin AND cloxacillin. A form with one drug-substance
    section describes half the product, and nothing on the page says so --
    the same defect P13 found in the QOS's structure images.
    """
    project = build_ampiclox()
    blocks = _qis(project)["substances"]

    assert [block.name for block in blocks] == ["Ampicillin", "Cloxacillin"]
    # Each block reads its OWN substance's leaves, so the two specifications
    # are not the same table.
    assert blocks[0].specification is not blocks[1].specification


def test_qis_impurity_limits_follow_the_substance():
    project = build_ampiclox()
    substance = project.product.apis[0]
    impurity = sorted(substance.impurities, key=lambda i: (i.impurity_type.value, i.name))[0]
    impurity.limit = "0.05 %"

    block = _qis(project)["substances"][0]
    assert any(row["limit"] == "0.05 %" for row in block.impurities)


def test_every_qis_field_names_a_leaf_it_came_from():
    """Provenance is checked, not just printed.

    Every value on the form carries the leaf it was derived from, and that
    leaf has to be one this project actually renders. A field claiming a
    source that does not exist is a field somebody wrote by hand and
    labelled.
    """
    project = build_ampiclox()
    context = _qis(project)
    rendered = set(section_contexts(project))

    sourced = list(context["general"]) + list(context["product_stability"])
    sourced += list(context["container"])
    for block in context["substances"]:
        sourced += list(block.identity) + list(block.stability)

    for item in sourced:
        if item.source == "1.2.2":
            # The one declared exception, documented in qis._applicant_name:
            # who is applying is not a quality fact and appears nowhere in
            # the body of data.
            assert item.label == "Applicant"
            continue
        assert item.source in rendered, f"{item.label} cites {item.source}, which is not rendered"


def test_the_qis_has_nothing_authorable_on_it():
    """No narrative slots, so there is no field a model or a human can
    write into. The same call 1.4.1 made, and for the same reason: a
    drafted sentence on an agency form is a regulatory claim that the
    section it summarises does not make."""
    assert get_section("1.4.2").narrative_slots == []
