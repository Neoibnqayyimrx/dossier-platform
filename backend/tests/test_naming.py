"""gap Phase 5a: file and folder names that ICH accepts.

Two kinds of test. The unit tests pin how app.ctd.naming spells a name.
The structural ones walk the REAL folder map and region profiles and prove
that nothing this platform can build breaks ICH's rules or the strictest
regional path limit -- including for a subject name longer than any real
one, because the budget in SUBJECT_MAX_LENGTH is only a number until
something checks it against the deepest folder that exists.
"""

from __future__ import annotations

import re
import uuid

import pytest

from app.ctd.naming import (
    ICH_NAME_MAX_LENGTH,
    abbreviate,
    ich_name,
    leaf_filename,
    placeholder_filename,
    subject_folder_name,
)
from app.ctd.region_profiles import REGION_PROFILES
from app.ctd.structure import MODULE_2_5_FOLDERS, REPEAT_FOLDERS, folder_for_section_instance
from app.ectd.backbone import REGIONAL_BACKBONES

# Written out from ICH v3.2.2 Appendix 2, independently of app.ctd.naming.
_ICH_FOLDER = re.compile(r"^[a-z0-9-]+$")
_ICH_FILE = re.compile(r"^[a-z0-9-]+\.[a-z0-9-]+$")
_STRICTEST_PATH_LIMIT = min(rb.max_path_length for rb in REGIONAL_BACKBONES.values())
_ABSURD_SUBJECT = "a-subject-name-longer-than-any-real-excipient-or-substance-" * 4


def _assert_ich_path(path: str) -> None:
    *folders, file_name = path.split("/")
    for folder in folders:
        assert _ICH_FOLDER.match(folder), (path, folder)
        assert len(folder) <= ICH_NAME_MAX_LENGTH, (path, folder)
    assert _ICH_FILE.match(file_name), (path, file_name)
    assert len(file_name) <= ICH_NAME_MAX_LENGTH, (path, file_name)


# ---- how names are spelled ----------------------------------------------------


@pytest.mark.parametrize(
    ("section_number", "suffix", "expected"),
    [
        ("3.2.P.1", None, "3-2-p-1.pdf"),
        ("3.2.S.4.1", None, "3-2-s-4-1.pdf"),
        ("1.0", None, "1-0.pdf"),
        ("5.3.1.2", "summary", "5-3-1-2-summary.pdf"),
    ],
)
def test_a_leaf_is_named_after_its_section_in_ich_characters(section_number, suffix, expected):
    assert leaf_filename(section_number, suffix) == expected


def test_ich_name_keeps_only_what_ich_allows():
    assert ich_name("Hydroxypropyl Methylcellulose (HPMC) 2910_E5") == (
        "hydroxypropyl-methylcellulose-hpmc-2910-e5"
    )


def test_abbreviation_is_deterministic_and_keeps_similar_names_apart():
    """Two excipients sharing a long prefix must not become one folder --
    that would be one document silently overwriting the other."""
    a = abbreviate("hydroxypropyl-methylcellulose-2910", 24)
    b = abbreviate("hydroxypropyl-methylcellulose-2208", 24)
    assert len(a) <= 24 and len(b) <= 24
    assert a != b
    assert a == abbreviate("hydroxypropyl-methylcellulose-2910", 24)
    assert abbreviate("short", 24) == "short"


def test_a_placeholder_is_named_by_type_and_a_short_id():
    identifier = uuid.UUID("aaadc800-d170-4c09-bb7f-50f3eb890ac6")
    assert placeholder_filename("certificate-of-incorporation", identifier) == (
        "certificate-of-incorporation-aaadc800.pdf"
    )
    assert placeholder_filename("CPP", identifier) == "cpp-aaadc800.pdf"


# ---- nothing the platform can build breaks the rules ---------------------------


def test_every_module_2_to_5_path_fits_the_strictest_region():
    for number, folder in MODULE_2_5_FOLDERS.items():
        path = f"0000/{folder}/{leaf_filename(number)}"
        _assert_ich_path(path)
        assert len(path) <= _STRICTEST_PATH_LIMIT, (len(path), path)


def test_a_repeated_section_fits_even_with_an_absurd_subject_name():
    """The test SUBJECT_MAX_LENGTH exists to pass. Every per-subject folder
    the platform knows, with a subject name longer than any real one, and
    the path must still be ICH-legal and inside FDA's 150 -- the strictest
    limit any configured region states."""
    for folders in REPEAT_FOLDERS.values():
        for number in folders.tails:
            path = (
                f"0000/{folder_for_section_instance(number, _ABSURD_SUBJECT)}/"
                f"{leaf_filename(number)}"
            )
            _assert_ich_path(path)
            assert len(path) <= _STRICTEST_PATH_LIMIT, (len(path), path)


def test_every_module_1_folder_and_placeholder_is_ich_legal():
    identifier = uuid.uuid4()
    for profile in REGION_PROFILES.values():
        for slot in profile.module1_slots:
            names = [leaf_filename(slot.section_number)] if slot.section_number else []
            names += [
                placeholder_filename(t.value, identifier)
                for t in (*slot.certificate_types, *slot.declaration_types)
            ]
            for name in names:
                _assert_ich_path(f"0000/{slot.folder}/{name}")
        for slot in profile.document_slots:
            _assert_ich_path(f"0000/{slot.folder}/{leaf_filename(slot.section_number)}")


def test_the_subject_is_abbreviated_in_the_path_but_not_in_the_identity():
    """The instance key (the lifecycle's section key, an upload's storage
    key) keeps the full slug; only the folder name is shortened."""
    folder = subject_folder_name("excipient", "anhydrous-dibasic-calcium-phosphate")
    assert folder.startswith("excipient-anhydrous-dibas-")
    assert len(folder) <= len("excipient-") + 24
