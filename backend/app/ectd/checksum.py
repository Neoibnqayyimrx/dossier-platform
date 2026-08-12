"""MD5 checksum utilities (P09).

Split out as its own tiny module (rather than inlined in `leaf.py`/
`build.py`) because it gets called from three independent places -- per-
leaf checksums, `index.xml`'s own checksum, and (P09's tamper-detection
test) re-checksumming a file after the fact to prove the number is real,
not a stored fiction.
"""

from __future__ import annotations

import hashlib


def md5_hex(data: bytes) -> str:
    """The file checksum every eCTD leaf and `index-md5.txt` uses.

    WHY MD5 specifically, not something stronger: this isn't a security
    choice. FDA's and EMA's published eCTD validation criteria, and the
    gateway validators that enforce them, check leaf checksums as MD5 --
    a leaf hashed with anything else would be internally consistent but
    gateway-invalid.
    """
    return hashlib.md5(data).hexdigest()


def index_md5_line(index_xml_bytes: bytes) -> str:
    """The single-line contents of `index-md5.txt`: `<md5>  index.xml`,
    two spaces, no trailing content -- the same format the standard
    `md5sum` CLI tool produces, which is the convention eCTD reviewer
    tools expect this file to be in."""
    return f"{md5_hex(index_xml_bytes)}  index.xml\n"
