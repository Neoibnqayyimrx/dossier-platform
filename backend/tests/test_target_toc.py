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

    # 1.2.11 has no CertificateType at all, so there is not even a slot.
    assert resolve_status(by_number["1.2.11"], producible) == "missing"


def test_status_is_never_hand_maintained_as_a_real_value():
    """Humans own applicable/production/repeat/data_sources/blocked_by/notes.

    `status` in the file is a placeholder the script overwrites; if someone
    starts curating it by hand it will drift from what the platform does.
    """
    target = load_target()
    assert {entry["status"] for entry in target["sections"]} == {"unknown"}
