# eCTD v3.2.2 backbone DTDs/stylesheets (real, unmodified)

Source: official EMA eSubmission "EU Module 1" utility package,
`util_zips/util (4).zip`, downloaded from
<https://esubmission.ema.europa.eu/eumodule1/> on 2026-08-12.

This is the same package a real EU eCTD submitter downloads — the ICH DTD
is bundled inside the EU package because EU's DTD imports it. These are
**unmodified copies** of publicly published implementer schemas, not
proprietary or copyrighted content (contrast with the P03 rule against
ingesting pharmacopoeia *text* — DTDs are technical interchange schemas
agencies publish specifically so software can build against them).

| File | What it is | DTD version (per file header) |
|---|---|---|
| `ich-ectd-3-2.dtd` | ICH backbone (`index.xml`) — common to every region | 3.2, Nov 2003 |
| `eu-regional.dtd` | EU regional backbone (`eu-regional.xml`) root | 3.1, Aug 2009 (rev. Jun 2024) |
| `eu-envelope.mod` | EU envelope element definitions (imported by `eu-regional.dtd`) | 3.1, Jun 2024 |
| `eu-leaf.mod` | EU `<leaf>`/`<node-extension>` defs, deliberately kept identical to the ICH ones | — |
| `ectd-2-0.xsl` | ICH's own stylesheet for human-readable rendering of `index.xml` | — |
| `eu-regional.xsl` | EU's stylesheet for `eu-regional.xml` | — |

`app/ectd/index_xml.py` and `app/ectd/regional.py` (P09) validate their
generated XML against `ich-ectd-3-2.dtd` and `eu-regional.dtd` respectively,
in-process via `lxml.etree.DTD`. `eu-regional.dtd` pulls in
`eu-envelope.mod`/`eu-leaf.mod` via `SYSTEM` entity references — all three
files must stay in this same directory for that resolution to work.

## FDA (gap Phase 4b)

Source: FDA's *eCTD Submission Standards for eCTD v3.2.2 and Regional M1*
page, whose download links all point at `www.accessdata.fda.gov/static/eCTD/`
(downloaded 2026-09-21). Unmodified copies, same reasoning as the EU set.

| File | What it is | Version (per file header / FDA's standards table) |
|---|---|---|
| `us-regional-v3-3.dtd` | FDA regional backbone (`m1/us/us-regional.xml`). Self-contained -- no `.mod` files | 3.3; required since 2022-03-01 |
| `us-regional.xsl` | FDA's stylesheet for `us-regional.xml` | 2.2 |
| `fda-code-lists/*.xml` | The coded values FDA's backbone uses (`fdaat2` = ANDA, `fdast1` = Original Application, ...) | per file `version-number` / `AsOf` |

WHY the code lists are vendored too, when the EU needed nothing similar:
FDA's DTD declares almost every admin attribute as bare `CDATA`
(`application-type`, `submission-type`, `submission-sub-type`, ...), so the
DTD accepts ANY string there. What makes a value legal is its presence, with
`status="active"`, in these lists -- "only coded values with a status of
'active' should be submitted" (FDA's *eCTD Backbone Files Specification for
Module 1*, v2.6, section I). `app/ectd/us_regional.py`'s code tables are
tested against these files rather than trusted, and mechanical check M13
(`app/ectd/validate.py`, gap Phase 4c) reads them again to judge every code
in a BUILT package.

The code lists change more often than the DTD (FDA publishes each one with
its own version). Re-download and re-run the tests when FDA's standards page
shows a newer version.
