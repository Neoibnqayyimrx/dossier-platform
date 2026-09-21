"""Sequence utility-file scaffolder (P09): the `util/dtd/` and
`util/style/` files every sequence ships alongside its backbones, copied
verbatim from `reference/ectd_dtd/` (see that directory's README for
provenance).

WHY this returns a flat `{relative_path: bytes}` dict rather than doing
real filesystem `mkdir`s: the builder's output is a zip (`app.ectd.build`),
where a folder only exists as the prefix of the files inside it, so there
is nothing to create -- a zip entry IS its folder. Same reasoning
`app.ctd.build` already uses.

This docstring used to add "there is nothing to scaffold for the empty
m4/m5 module folders this project doesn't populate". That was true and it
was the bug: m4 and m5 were empty because applicability was implicit in
which sections happened to be registered, and an empty m4 looks to an
assessor exactly like a packaging failure. Since P17 those folders are not
empty -- they carry the generated not-applicable statements the source
dossier files there, produced through the ordinary section pipeline (see
`app.ctd.region_profiles`' applicability table). Nothing extra is scaffolded
here because nothing extra needs to be: a statement leaf is a leaf.
"""

from __future__ import annotations

from pathlib import Path

_DTD_SOURCE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "reference" / "ectd_dtd"

# The ICH-level util files are the same for every region; the regional DTD,
# its modules and its stylesheet come from the region's entry in
# app.ectd.backbone.REGIONAL_BACKBONES (gap Phase 4b) -- one table per
# region rather than one here and another there that could disagree.
_COMMON_UTIL_FILES = {
    "util/dtd/ich-ectd-3-2.dtd": "ich-ectd-3-2.dtd",
    "util/style/ectd-2-0.xsl": "ectd-2-0.xsl",
}


def scaffold_files(regional_util_files: dict[str, str]) -> dict[str, bytes]:
    """`{util path: bytes}` for one sequence: the ICH files plus
    `regional_util_files` (util path -> file name in reference/ectd_dtd/)."""
    files: dict[str, bytes] = {}
    for rel_path, source_name in {**_COMMON_UTIL_FILES, **regional_util_files}.items():
        files[rel_path] = (_DTD_SOURCE_DIR / source_name).read_bytes()
    return files
