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

**FDA is not covered.** P09 built the EU region only (Region.FDA is a valid
enum member but has no `RegionProfile`/DTD yet) — see the P09 build-log
entry for the scope call.
