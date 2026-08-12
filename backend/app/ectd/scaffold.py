"""Sequence utility-file scaffolder (P09): the `util/dtd/` and
`util/style/` files every sequence ships alongside its backbones, copied
verbatim from `reference/ectd_dtd/` (see that directory's README for
provenance).

WHY this returns a flat `{relative_path: bytes}` dict rather than doing
real filesystem `mkdir`s: the builder's output is a zip (`app.ectd.build`),
where a folder only exists as the prefix of the files inside it -- there
is nothing to scaffold for the empty m4/m5 module folders this project
doesn't populate, so nothing is emitted for them. Same "a zip entry IS the
folder" reasoning `app.ctd.build` already uses.
"""

from __future__ import annotations

from pathlib import Path

_DTD_SOURCE_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "reference" / "ectd_dtd"
)

# WHY only the EU regional files are conditional (FDA has none yet): the
# ICH-level util files are the same for every region -- only the regional
# DTD/envelope/leaf modules and stylesheet differ.
_COMMON_UTIL_FILES = {
    "util/dtd/ich-ectd-3-2.dtd": "ich-ectd-3-2.dtd",
    "util/style/ectd-2-0.xsl": "ectd-2-0.xsl",
}
_EU_UTIL_FILES = {
    "util/dtd/eu-regional.dtd": "eu-regional.dtd",
    "util/dtd/eu-envelope.mod": "eu-envelope.mod",
    "util/dtd/eu-leaf.mod": "eu-leaf.mod",
    "util/style/eu-regional.xsl": "eu-regional.xsl",
}


def scaffold_files(region: str) -> dict[str, bytes]:
    if region != "eu":
        raise NotImplementedError(f"No util/dtd scaffold for region {region!r} yet (EU only)")

    files: dict[str, bytes] = {}
    for rel_path, source_name in {**_COMMON_UTIL_FILES, **_EU_UTIL_FILES}.items():
        files[rel_path] = (_DTD_SOURCE_DIR / source_name).read_bytes()
    return files
