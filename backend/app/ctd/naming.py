"""File and folder names in a package (gap Phase 5a).

ICH eCTD Specification v3.2.2, Appendix 2: a name "is a token composed of"
the letters a-z, the digits 0-9 and the hyphen; "Only lower case letters
should be used"; a file name is one name, a full stop, and one extension;
"The maximum length of the name of a single folder or file is 64
characters including the extension." Uppercase, full stops inside a name,
underscores and spaces are all listed as INCORRECT, by example.

Until this phase every leaf was named after its instance key --
`3.2.P.1.pdf`, `3.2.S.4.1-cloxacillin.pdf` -- which broke that rule for
two thirds of every package this platform built. The fix lives here, in
one module, because three places name files (assembly, and both builders'
certificate and declaration placeholders) and they had each spelled the
name out for themselves.

WHY the section number stays in the name: an assessor reading `3-2-p-1.pdf`
still knows what they are looking at. ICH's own recommended file names
(Appendix 4) are descriptive words, but they are optional, and the number
is what this platform, its target TOC and a filer all navigate by.

WHY the instance key itself is NOT renamed: it is also the lifecycle's
section key (SequenceLeaf.section_key) and the key an uploaded document is
stored under (SectionDocument.instance_key). Changing it would make every
existing project's next sequence re-file every repeated leaf as new. The
key is identity; this module only decides how that identity is spelled in
a path.
"""

from __future__ import annotations

import hashlib
import re

# ICH v3.2.2 Appendix 2.
ICH_NAME_MAX_LENGTH = 64

# The subject part of a per-subject folder ("excipient-<subject>",
# "32s-<substance>"), at most this long. NOT a spec number: it is derived
# from the deepest folder in app.ctd.structure and FDA's 150-character path
# limit, the strictest a region states, so that no subject however long can
# push a path over it. tests/test_naming.py re-derives the worst path from
# the real folder map and fails if this stops being enough -- the constant
# is only trusted because that test exists.
SUBJECT_MAX_LENGTH = 24

_NOT_A_NAME_CHARACTER = re.compile(r"[^a-z0-9]+")
_HASH_LENGTH = 8


def ich_name(text: str) -> str:
    """`text` as an ICH name token: lowercase, and every run of anything
    that is not a-z or 0-9 becomes one hyphen. "3.2.P.1" -> "3-2-p-1"."""
    return _NOT_A_NAME_CHARACTER.sub("-", text.lower()).strip("-")


def abbreviate(name: str, limit: int) -> str:
    """`name` at most `limit` characters, deterministically.

    WHY a hash rather than a plain cut: two long names that share their
    first `limit` characters -- two excipients both starting
    "hydroxypropyl-methylcellulose-" -- would otherwise abbreviate to the
    SAME folder, and one document would overwrite the other in the zip with
    nothing to say so. A short hash of the full name keeps them apart and
    is the same every build, so a package still rebuilds byte-identically.
    ICH asks for exactly this order of work: abbreviate the names the
    applicant created before touching the ones the specification recommends.
    """
    if len(name) <= limit:
        return name
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
    head = name[: limit - _HASH_LENGTH - 1].rstrip("-")
    return f"{head}-{digest}"


def leaf_filename(section_number: str, suffix: str | None = None) -> str:
    """The file name a leaf ships under: "3.2.P.1" -> "3-2-p-1.pdf".

    Deliberately WITHOUT the subject. A repeated section already sits in a
    folder of its own per subject (app.ctd.structure), and putting the
    subject in the file name as well is what made the longest path in the
    worked example 167 characters -- the name appeared twice. `suffix`
    (SectionSpec.leaf_suffix, e.g. "summary") is kept, because a generated
    summary and the uploaded report it accompanies share one folder.
    """
    stem = ich_name(section_number if suffix is None else f"{section_number}-{suffix}")
    return f"{abbreviate(stem, ICH_NAME_MAX_LENGTH - len('.pdf'))}.pdf"


def subject_folder_name(prefix: str, subject_slug: str) -> str:
    """ "excipient-anhydrous-dibasic-calcium-phosphate" becomes
    "excipient-anhydrous-dibas-<8 hex>": the subject abbreviated so the
    deepest path stays inside FDA's limit (see SUBJECT_MAX_LENGTH)."""
    return f"{prefix}-{abbreviate(ich_name(subject_slug), SUBJECT_MAX_LENGTH)}"


def placeholder_filename(kind: str, identifier: object) -> str:
    """A certificate or declaration placeholder: its type, then the first
    eight characters of its id -- enough to tell two certificates of one
    type apart, where the full UUID pushed four names past 64 characters.
    "certificate-of-incorporation-aaadc800.pdf", not "...-aaadc800-d170-4c09-
    bb7f-50f3eb890ac6.pdf"."""
    stem = ich_name(f"{kind}-{str(identifier)[:_HASH_LENGTH]}")
    return f"{abbreviate(stem, ICH_NAME_MAX_LENGTH - len('.pdf'))}.pdf"
