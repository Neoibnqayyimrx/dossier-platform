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


# ---- P24c: the QOS cannot diverge from Module 3 -----------------------------


def _qos(project) -> dict:
    from app.templating.qos import qos_context

    return qos_context(get_section("2.3"), project, narrative=None)


def _subsection(context: dict, number: str, substance_index: int = 0) -> object:
    """One numbered QOS subsection, by its 2.3.x number."""
    if number.startswith("2.3.S"):
        subsections = context["drug_substances"][substance_index]["subsections"]
    else:
        subsections = context["drug_product_subsections"]
    return next(sub for sub in subsections if sub.number == number)


def test_qos_has_every_subsection_the_target_declares():
    """Fourteen, per the target's `covers` list on 2.3.

    "Registered" and "complete" were different statuses for this leaf from
    P04 until P24 -- it rendered a heading, the structural formulae and one
    paragraph while the contract listed fourteen subsections. This is what
    closes that gap, and what stops it reopening.
    """
    project = build_examox(buggy=False)
    context = _qos(project)

    substance = [sub.number for sub in context["drug_substances"][0]["subsections"]]
    product = [sub.number for sub in context["drug_product_subsections"]]

    assert substance == [f"2.3.S.{n}" for n in range(1, 8)]
    assert product == [f"2.3.P.{n}" for n in range(1, 8)]
    assert len(substance) + len(product) == 14


def test_qos_shelf_life_follows_module_3():
    """The defect this platform exists to eliminate, in one assertion.

    A QOS that states a retest period 3.2.S.7.1 does not is the most
    commonly raised quality deficiency there is, and it is never a decision
    -- it is a second copy of a number, updated once.
    """
    project = build_examox(buggy=False)
    substance = project.product.apis[0]

    before = _subsection(_qos(project), "2.3.S.7").values[0].value
    substance.retest_period_months = 6
    after = _subsection(_qos(project), "2.3.S.7").values[0].value

    assert before != after
    assert after == build_context("3.2.S.7.1", project, subject=substance)["claim_statement"]


def test_qos_specification_follows_module_3():
    project = build_examox(buggy=False)
    project.product.specification[0].acceptance_criterion = "99 % to 101 %"

    rows = _subsection(_qos(project), "2.3.P.5").table_rows
    assert any("99 % to 101 %" in row["cells"] for row in rows)


def test_qos_composition_follows_the_batch_formula():
    project = build_examox(buggy=False)
    project.product.batch_formula[0].component = "Renamed Component BP"

    rows = _subsection(_qos(project), "2.3.P.1").table_rows
    assert any(row["cells"][0] == "Renamed Component BP" for row in rows)


def test_qos_impurity_limits_follow_module_3():
    project = build_ampiclox()
    substance = project.product.apis[0]
    impurity = sorted(substance.impurities, key=lambda i: (i.impurity_type.value, i.name))[0]
    impurity.limit = "0.02 %"

    rows = _subsection(_qos(project), "2.3.S.3").table_rows
    assert any("0.02 %" in row["cells"] for row in rows)


def test_qos_repeats_per_drug_substance():
    """A combination product owes a 2.3.S block per active.

    A QOS summarising "the drug substance" of a two-active product
    summarises one material and says nothing about which -- and 2.3.S is
    the half of the QOS an assessor reads to decide whether the API case
    holds.
    """
    project = build_ampiclox()
    blocks = _qos(project)["drug_substances"]

    assert [block["name"] for block in blocks] == ["Ampicillin", "Cloxacillin"]
    ampicillin = _subsection(_qos(project), "2.3.S.4", substance_index=0)
    cloxacillin = _subsection(_qos(project), "2.3.S.4", substance_index=1)
    assert ampicillin.values[0].value != cloxacillin.values[0].value


def test_qos_cannot_state_a_retest_period_module_3_refuses_to_print():
    project = build_examox(buggy=False)
    project.product.apis[0].retest_period_months = 900

    stated = _subsection(_qos(project), "2.3.S.7").values[0].value
    assert "NOT SUPPORTED" in stated


def test_every_qos_subsection_names_the_module_3_section_it_mirrors():
    """The navigation contract. 2.3.S.4 must say it summarises 3.2.S.4.

    A QOS subsection that does not name what it mirrors makes the reviewer
    do the mapping in their head, which is the one thing the ICH M4Q
    structure exists to spare them.
    """
    project = build_examox(buggy=False)
    context = _qos(project)

    for block in context["drug_substances"]:
        for sub in block["subsections"]:
            assert sub.mirrors == sub.number.replace("2.3.", "3.2.")
    for sub in context["drug_product_subsections"]:
        assert sub.mirrors == sub.number.replace("2.3.", "3.2.")


def test_qos_narrative_slots_are_summary_only():
    """Three slots, and none of them can carry a figure.

    Not because a model would be asked politely: every number in the
    document is printed from the derived blocks above the slots, so a
    contradiction appears on the same page rather than three hundred pages
    away. What the slots hold is the argument -- which is genuinely the
    applicant's to make.
    """
    slots = get_section("2.3").narrative_slots
    assert slots == ["overview", "drug_substance_summary", "drug_product_summary"]


def test_qos_and_qis_agree_because_neither_holds_its_own_copy():
    """The two derived documents, cross-read the way an assessor reads them.

    A QIS and a QOS stating two different specifications is a real filing
    defect and an obvious one. Here they cannot: both read 3.2.P.5.1's
    rendered rows, so there is one table and two documents printing it.
    """
    project = build_examox(buggy=False)
    project.product.specification[0].acceptance_criterion = "97.5 % to 102.5 %"

    qis_rows = _qis(project)["product_specification"]
    qos_rows = _subsection(_qos(project), "2.3.P.5").table_rows

    assert qis_rows[0]["acceptance_criterion"] == "97.5 % to 102.5 %"
    assert qos_rows[0]["cells"][2] == "97.5 % to 102.5 %"
