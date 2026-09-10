"""The target TOC is a contract, so it gets tests like any other contract.

P16: `docs/target-toc.yaml` decides what "a finished dossier" means, and
`scripts/check_target_toc.py` decides what counts as produced. Both are only
worth trusting if the file they read is internally consistent -- a `blocked_by`
naming a capability that does not exist silently unblocks its leaf, and nothing
about reading the YAML would show it.
"""

from __future__ import annotations

from scripts.check_target_toc import load_target, producible_keys, resolve_status


def test_every_blocker_names_a_declared_capability():
    """A typo'd blocker is invisible: the leaf just stops being blocked.

    `blocked_by: [uplaod_path]` still parses, still counts, and still gets
    reported -- under a capability heading nobody recognises. Worse, once the
    capability it meant to name is built, the leaf never unblocks. Assert the
    reference resolves.
    """
    target = load_target()
    capabilities = set(target["capabilities"])

    unknown = {
        (entry["number"], blocker)
        for entry in target["sections"]
        for blocker in entry.get("blocked_by") or []
        if blocker not in capabilities
    }

    assert not unknown, f"blocked_by names undeclared capabilities: {sorted(unknown)}"


def test_every_leaf_declares_a_known_production_type():
    target = load_target()
    declared = set(target["production_types"])
    unknown = {
        (entry["number"], entry["production"])
        for entry in target["sections"]
        if entry["production"] not in declared
    }
    assert not unknown, f"unknown production types: {sorted(unknown)}"


def test_module1_declarations_are_credited():
    """1.2.4-1.2.6 render today via templating/declarations.py.

    They have no registry entry, so a check reading only the registry called
    them `missing`. That is the single-source defect P16 fixed; this pins it.
    """
    target = load_target()
    producible = producible_keys(target["sections"])
    by_number = {entry["number"]: entry for entry in target["sections"]}

    for number in ("1.2.4", "1.2.5", "1.2.6"):
        assert resolve_status(by_number[number], producible) == "done"


def test_certificate_slots_are_placeholders_not_documents():
    """The distinction the whole check exists for.

    A CPP slot with folder placement and a placeholder path is not a CPP. It
    reads `placeholder` -- neither `missing` (the slot is real) nor `done`
    (the document is not).
    """
    target = load_target()
    producible = producible_keys(target["sections"])
    by_number = {entry["number"]: entry for entry in target["sections"]}

    assert resolve_status(by_number["1.2.7"], producible) == "placeholder"
    assert resolve_status(by_number["1.2.8"], producible) == "placeholder"

    # 1.2.11 had no CertificateType at all when P16 wrote this, so there was
    # not even a slot. P18 added the type AND a Module 1 document slot, so it
    # now reads `placeholder` -- a place for the file exists, the file does
    # not. That is the state changing for the right reason; `done` would
    # still be wrong, and that is what this line now guards.
    assert resolve_status(by_number["1.2.11"], producible) == "placeholder"
    assert resolve_status(by_number["1.2.11"], producible, {"1.2.11"}) == "done"


def test_status_is_never_hand_maintained_as_a_real_value():
    """Humans own applicable/production/repeat/data_sources/blocked_by/notes.

    `status` in the file is a placeholder the script overwrites; if someone
    starts curating it by hand it will drift from what the platform does.
    """
    target = load_target()
    assert {entry["status"] for entry in target["sections"]} == {"unknown"}


# ---- P24e: the gate ---------------------------------------------------------


def test_every_leaf_has_a_route_to_production():
    """The contract, closed. This is what `--strict` runs in CI.

    Asserted here as well as in CI so that the failure arrives with a name
    attached: CI prints the report, and this prints the leaf.
    """
    from scripts.check_target_toc import PLATFORM, is_gap

    target = load_target()
    producible = producible_keys(target["sections"])

    without_a_route = [
        (entry["number"], resolve_status(entry, producible))
        for entry in target["sections"]
        if is_gap(resolve_status(entry, producible), PLATFORM)
    ]
    assert not without_a_route, f"leaves with no route to production: {without_a_route}"


def test_a_placeholder_is_a_route_for_the_platform_but_not_for_a_filing():
    """The distinction the whole two-scope design rests on.

    A CPP placeholder means the platform can place the certificate when it
    arrives -- which is everything the platform can do, since nobody here
    can author a regulator's certificate. It does NOT mean the CPP is in,
    and for a named project it is exactly the gap.

    Getting this wrong in either direction is expensive: treat a
    placeholder as done for a filing and the platform reports a complete
    dossier that is missing eleven documents; treat it as a gap for the
    platform and CI is red on every commit forever.
    """
    from scripts.check_target_toc import PLATFORM, PROJECT, is_gap

    target = load_target()
    producible = producible_keys(target["sections"])
    cpp = next(e for e in target["sections"] if e["number"] == "1.2.7")

    status = resolve_status(cpp, producible)
    assert status == "placeholder"
    assert not is_gap(status, PLATFORM)
    assert is_gap(status, PROJECT)

    # And with the document actually attached, it is done in both scopes.
    attached = resolve_status(cpp, producible, {"1.2.7"})
    assert attached == "done"
    assert not is_gap(attached, PROJECT)


def test_strict_would_fail_on_a_leaf_with_nowhere_to_come_from():
    """The gate has to be able to FAIL, or it is decoration.

    A synthetic leaf, checked through the same resolver CI uses: a newly
    declared applicable section with no registry entry, no folder and no
    slot is `missing`, and `missing` fails in both scopes.
    """
    from scripts.check_target_toc import PLATFORM, PROJECT, is_gap

    invented = {
        "number": "3.2.P.9",
        "module": 3,
        "title": "A section nobody has built",
        "applicable": True,
        "production": "generated",
        "status": "unknown",
    }
    status = resolve_status(invented, producible_keys(load_target()["sections"]))
    assert status == "missing"
    assert is_gap(status, PLATFORM)
    assert is_gap(status, PROJECT)


def test_a_filing_that_scopes_a_leaf_out_does_not_owe_it():
    """The third state project scope needed (P24e).

    A conditional leaf answered "no" is a scoping ANSWER, not missing
    paper. Without it, no correct filing could ever reach 98/98 -- and the
    number would have pushed a filer to attach *something* at a leaf they
    had already declared out of scope, which is how a dossier acquires a
    document contradicting its own answers.

    Exercised through `not_owed_from` rather than `not_owed_keys` because
    the latter needs a live Postgres: a gate whose logic is only ever run
    against a real database is a gate nobody notices breaking.
    """
    from app.models.enums import Region, SubmissionType
    from scripts.check_target_toc import PROJECT, is_gap, not_owed_from

    answers = {"1.2.13": False, "1.2.17": False, "5.3.1.1": False}
    not_owed = not_owed_from(Region.NAFDAC, SubmissionType.MULTISOURCE_GENERIC, answers)

    # The three answered "no" are not owed...
    assert {"1.2.13", "1.2.17", "5.3.1.1"} <= not_owed
    # ...and so are the sections the multisource guideline excludes outright.
    assert {"2.4", "2.5", "4.0"} <= not_owed
    # ...but a required leaf is still owed, whatever the answers say.
    assert "3.2.P.5.1" not in not_owed
    assert "1.2.7" not in not_owed

    assert not is_gap("not-owed", PROJECT)


def test_an_unanswered_conditional_is_still_owed():
    """Silence is not a "no".

    An unanswered conditional must NOT be quietly scoped out -- that is
    precisely how a biowaiver claim goes missing from a dossier that
    otherwise validates clean, which is the failure rule R19 exists to
    warn about. The check has to agree with the rule.
    """
    from app.models.enums import Region, SubmissionType
    from scripts.check_target_toc import not_owed_from

    not_owed = not_owed_from(Region.NAFDAC, SubmissionType.MULTISOURCE_GENERIC, {})

    assert "1.2.17" not in not_owed
    assert "1.2.13" not in not_owed
