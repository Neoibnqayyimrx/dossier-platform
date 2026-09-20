# Build Log

The running record of what this platform is and why it is that way. It
covers every phase from P00 onward, plus the unplanned interludes that
turned out to matter as much as the phases.

## When to write here

Not only at the end of a phase. Append (or extend the entry in progress)
whenever any of these happens:

- a phase or slice is finished;
- a capability, endpoint, model, or migration is added;
- **a real problem is solved** — a bug, a wrong assumption, a misleading
  symptom, a gotcha in a library, a spec that didn't behave as expected;
- a scope call or deliberate deferral is made.

## What makes an entry worth reading

Record the **why**, not just the what: the reasoning, the alternative that
was rejected and what was wrong with it, and — for a bug — *how it
actually announced itself*, since that's what makes it recognisable the
second time. Say plainly when something is a known gap, a proxy, or an
MVP simplification; a log that only records successes is a marketing
document.

Most of this project's value lives in this file. A fix that isn't written
down gets re-debugged from scratch six weeks later.

Newest entry at the top.

---

## Phase 2 — a document's history, and the fixed-key trap again (2026-09-20)

P18 said replacing an upload overwrites it, and justified that by pointing
at eCTD's sequence-level lifecycle. The justification is half right, and
the missing half is the whole phase: sequence history covers what was
FILED. Between two sequences a leaf can be replaced any number of times,
and each replacement destroyed its predecessor's bytes irrecoverably. "Who
replaced the CPP in April, and what did it say in March?" had no answer.

### The shape, and the cost of the shape

`document_version`: one immutable row per upload. `SectionDocument` stays
the CURRENT version and keeps its file columns.

WHY not an `is_current` flag on one table, which is the tidier schema:
every consumer -- assemble.py (twice), the lifecycle resolver, the
validation rules -- already reads `document.storage_key` and
`document.md5`. Folding the columns away means each of them learns about
versioning in order to keep doing exactly what it does now. The unique
constraint that stops two files landing at one leaf would also have to
become a partial index over `is_current`, turning an unconditional
guarantee into a conditional one.

The cost, named honestly: the file columns on SectionDocument are a
DENORMALISATION of the newest version row. Two places hold the same five
values and no constraint forces them to agree. What makes it acceptable is
that there is exactly one writer and a test asserting the invariant
directly. A second writer would change that calculus.

### The fixed-key trap, for the second time this week

Phase 1a's listener bug was a fixed PORT. This was a fixed KEY, and it is
the same shape of mistake: under P18 every upload for a leaf wrote to
`projects/{id}/documents/{leaf}.pdf`, so a replacement overwrote its
predecessor in the bucket. Version rows pointing at a key whose bytes had
since been replaced would be a history that LIES -- strictly worse than
having no history, because it looks authoritative.

Each version now owns its key. That was only safe to change because
`storage_key_for` turned out to have exactly one caller and every consumer
READS `document.storage_key` rather than reconstructing it -- checked
first, not assumed, because if anything had rebuilt the path the change
would have silently served the wrong file.

Backfilled rows deliberately keep the OLD key. Their bytes really are
there, under really that key; rewriting it to look like the new convention
would put a false statement in the audit trail the table exists to provide.

### Gotchas banked

- **MissingGreenlet, the fifth time.** `document.versions.append(...)` on an
  existing row lazy-loads the collection. Fixed with `selectinload` on the
  upload query. The lesson this codebase keeps re-learning: on the async
  engine, any relationship you TOUCH must have been loaded, and "touch"
  includes appending to a collection.
- **A migration that round-trips values through Python is dialect-coupled.**
  Reading rows and bulk-inserting them re-marshals every value through
  SQLAlchemy's type system, and the types coming back differ -- Postgres
  hands back UUID and datetime objects, SQLite hands back strings. It broke
  twice in a row ("'str' object has no attribute 'hex'", then "SQLite
  DateTime type only accepts Python datetime"). Rewritten as a text
  INSERT..SELECT so the values never leave the database: nothing to convert,
  nothing to get wrong. Only the new ids come from Python, because
  `gen_random_uuid()` is Postgres-only.
- **A test helper that swallows its own setup failure is worse than no
  test.** The R30 fix added a product-information PUT to a helper; it
  returned 422 (`contraindications` is a list, not prose) and the test went
  on to assert against a dossier it had never actually completed. One
  `assert response.status_code == 200` found it immediately. Every setup
  step in a helper should assert it worked.
- **An eager load can be short by more than one level.** Fixing
  `product-information`'s MissingGreenlet by loading `Product.stability`
  was still wrong: the chain runs stability -> results ->
  `meets_criterion` -> that result's SPECIFICATION TEST. Three levels. The
  regression test caught the incomplete fix, which is the argument for
  writing the test before believing the fix.

### Stale tests, and why CI had been red

Three tests failed at HEAD for reasons unrelated to any of this work, and
had since P23/P24d. `test_ctd_build`'s EXPECTED_PATHS still named
`1.2.pdf` after P24d renumbered it to `1.2.2` (1.2 is a HEADING, not a
document) and still expected `power-of-attorney-<uuid>.pdf` after
declarations moved to their leaf numbers 1.2.4/1.2.5. `test_module1_api`
predated rule R30 and never entered product information.

The R30 one was fixed by COMPLETING the dossier through the API rather
than relaxing the assertion: "no seeding, nothing behind the API's back"
is the claim that test exists to make, and weakening it would have kept
the test green while deleting its meaning.

Backend: `30 failed, 519 passed` at the audit baseline -> `557 passed, 14
skipped, 0 failed`. CI is green for the first time in this sequence of
phases.

---

## Phase 1a — LibreOffice was the whole bill (2026-09-18)

The suite took 1:11:14 and everyone assumed "PDF rendering is just slow".
It was not rendering. It was starting.

### The number that decided it

    convert a 1-paragraph .docx     1109 ms
    convert a 400-paragraph .docx   1134 ms

399 extra paragraphs cost 25 ms. Laying out a page was tens of
milliseconds; the other ~1.1 s of every conversion -- about 98% of it --
was forking `soffice`, building a throwaway
user profile, registering import/export filters and bootstrapping UNO --
paid again for every document, and a NAFDAC package has dozens of leaves.

**The first measurement was wrong, and that is the useful part.** Timing
`soffice --version` as a proxy for startup gave 107 ms -- 8% of a call --
which says "startup is not your problem" and would have ended the phase
before it began. `--version` prints and exits; it never loads the filters
or the UNO bridge that a real conversion pays for. The honest probe is to
push the SMALLEST POSSIBLE document through the REAL code path: whatever
that costs is fixed overhead, because there is nothing to lay out. Worth
remembering the next time something here is benchmarked -- measure the real
path, not a cheaper thing that resembles it.

### The fix, and what was deliberately not changed

Start LibreOffice once and keep it. `app/assembly/converter.py` now owns
the transport behind a `DocumentConverter` protocol; `pdf.py` keeps the
contract (deterministic, bookmarked, normalized) and applies it to whatever
any transport returns.

Warm conversion went 1109 ms -> 206 ms for a real section, 6.0x, ~924 ms
saved per document. The rendering engine was NOT
replaced: LibreOffice's DOCX fidelity is why P07 chose it and that reasoning
still holds. The `lru_cache(256)` stayed too -- it helps only for identical
input, which is orthogonal.

**unoserver over a hand-rolled UNO bridge.** The bridge is ~150 lines and I
could have written it. unoserver won mainly because it keeps the client OUT
of our process: the API worker never imports `uno`, which matters because
pyuno is a compiled binding built against the DISTRO's Python rather than
ours, and because a LibreOffice crash then cannot take an API worker with
it. Costs ~100 ms per call for spawning the client. Recorded in
docs/decisions/0002-document-converter.md.

### The check that actually mattered

Byte-identical output, same MD5 from both transports. Not a nicety: P09's
checksums ARE hashes of these bytes, and `resolve_lifecycle` decides `new`
vs `replace` by comparing a leaf's checksum against the previous sequence.
A transport that changed the output by one byte would have marked every
unchanged document in the dossier as modified in the next sequence -- a
defect visible to a regulator, produced by a change that looked purely
internal. There is now a test asserting the two transports agree exactly.

### Gotchas banked

- **A process-wide singleton needs a restart path.** The listener is built
  once and cached, so without automatic restart one crash fails every
  conversion for the rest of the process's life -- the API would keep
  accepting builds and keep failing them. Restart once, then propagate: if
  a fresh listener also fails, the document is the problem.
- **One UNO listener is not safely reentrant.** Concurrent conversions
  through a single bridge interleave document open/close. Serialized with a
  lock; at ~200 ms a conversion that is not the bottleneck. More throughput
  means more listeners on more ports, never dropping the lock.
- **A fixed port for a singleton is a trap, and it fails as a LOOP not an
  error.** The listener originally used a fixed port (2003). A listener
  orphaned by an earlier run still held it, so the next one could not bind
  -- and because the failure surfaced as "conversion failed" rather than
  "port in use", the restart-on-failure path fired, spawned another, and
  repeated. The symptom was not an exception: it was the suite crawling at
  ~14 s per test with five listeners alive at once, each burning CPU. The
  fix is to bind port 0 and let the kernel choose, so collision is
  impossible; an explicit port remains available for when something
  external must reach the listener. Second fix in the same area: anything
  that escaped `_start()` left `self._process` set and running, so
  `_is_running()` reported healthy forever after -- every failure path now
  tears the process down before propagating.

- **`python3-uno` cannot be pip-installed** and is built against the
  distro's Python. If the project interpreter is a different minor version,
  `import uno` fails and the listener never starts. CI now checks this
  explicitly as an early step, because the alternative is a few hundred
  conversion failures that do not name their cause. This is the most likely
  thing to break on a new platform.
- **Benchmarks on a shared box lie.** A re-run while another test suite was
  saturating the machine (load average 9.7) inflated every number ~5x --
  6438 ms -> 1431 ms instead of 1109 -> 206. The RATIO held (4.5x vs 6.0x).
  Trust ratios over absolutes unless the machine is quiet -- and re-measure
  on an idle box before writing a number into a document.

### Gotenberg, as a real option rather than a sentence

Added behind a docker-compose profile and `DOCUMENT_CONVERTER=gotenberg`,
with a test that runs against a live container and skips when none is up
(the same courtesy the Postgres fixtures extend). It is the answer for
"LibreOffice should not be in the API container at all". Not the default:
it needs infrastructure, and the listener gets the same win without any.

---

## Gap Phase 0-1 — The NAFDAC format question, and four landmines (2026-09-18)

Working from `gap.md`: a phased plan to close the distance to a
LORENZ/Extedo-class platform. Phase 0 was research, Phase 1 was hygiene.

### NAFDAC does not need an eCTD backbone, and now we can prove it

The whole build has assumed NAFDAC = CTD, no XML backbone. That assumption
was inherited from `reference/nafdac-vs-fda-ema-scope.md` and had never been
checked against NAFDAC's own current guidance. Phase 0 checked it.

NAFDAC's in-force guideline (DR&R-GDL-005-03, effective 20/03/2025, review
21/03/2030) requires the CTD dossier format uploaded to the NAPAMS/DMS
portal. The load-bearing evidence is negative: across 12 pages it mentions
eCTD, XML, backbone, checksum, MD5 and sequence **zero times**. An applicant
cannot infer an XML backbone; an agency requiring one has to say so. Its
total absence from the registration guideline is decisive.

WHY this mattered enough to spend a phase on: it decides where the second
publishing backbone goes. Had we guessed "NAFDAC next" we would have built a
`NAFDACBackboneBuilder` producing a package NAFDAC cannot consume, and
implied to users that their Nigerian filing needs machinery it does not.
The second backbone goes to **FDA** instead, which genuinely rejects
non-conforming packages at the gateway. Written up in
`docs/decisions/0001-nafdac-format.md`.

**A blocker that surfaced while deciding:** `reference/ectd_dtd/` has the
ICH DTD and the EU regional set, but **no US regional DTD**. The FDA path
cannot self-validate the way the EU path does until that is obtained. Better
to know now than halfway through building it.

### The sequence-numbering race was real, and reproducible

`create_sequence` read `max(number)` then inserted — two statements, no
constraint. The audit flagged it as theoretical. It is not: with the
constraint removed, five concurrent POSTs against real Postgres returned
`0000, 0001, 0001, 0001, 0002`. Three sequences sharing a number.

WHY that is worse than an ordinary duplicate row: the sequence number is the
id the AGENCY files the submission under, and a lifecycle operation in 0003
points back at a leaf in 0002 *by that number*. Duplicates are not a display
bug, they are a submission history that cannot be read back, and they are
unrepairable once filed because the agency already has the number we gave it.

Fix: `UniqueConstraint("project_id", "number")` as the guarantee, bounded
retry as the recovery, 503 rather than a number we cannot prove is unique.

**Rejected: a Postgres advisory lock.** It serializes writers more directly
and avoids the retry entirely — but the suite also runs on SQLite
(`tests/conftest.py`), and a guarantee that holds on only one backend is not
a guarantee.

The migration **refuses to run** if duplicates already exist, listing them,
rather than picking a survivor. Renumbering a filed transaction id is a
regulatory decision, not a data-cleanup step.

**Gotcha worth remembering:** the obvious test — fire concurrent POSTs at
the default `auth_client` — does not work and does not fail honestly. The
in-memory SQLite fixture uses a StaticPool (one shared connection), so
concurrent requests corrupt the connection itself (`sqlite3.OperationalError:
no active connection`) rather than racing. A race test on that fixture tests
the fixture. The real test needs Postgres, which gives each session its own
connection; it skips when Postgres is not up.

### The failing storage tests were the environment leaking in

Two `test_artifacts_api.py` tests failed for developers with
`STORAGE_PROVIDER=s3` set. Symptom: `EndpointConnectionError` from botocore,
which reads like a MinIO problem and is actually a test-isolation problem.

Cause: most of the app takes storage as an injectable argument
(`storage = storage or get_storage_client()`), which is why every other test
hands in an `InMemoryStorageClient`. The API **routers** cannot —
`artifacts.py` and `documents.py` call `get_storage_client()` with no
injection point — so router tests silently inherit whatever the ambient
environment resolves to.

Fix: an autouse fixture pinning storage to memory and clearing the
`@lru_cache` on the way in and out. Ambient environment must never decide
whether a test passes.

Note the audit's premise here was wrong: `.env` is **not** committed, it is
gitignored, and `.env.example` already matches the code default.

### The frontend had no CI job at all

Not "an incomplete one" — none. Vitest (73 tests) and the Playwright spec
were both configured and neither had ever run in CI, so a frontend
regression merged with a green tick. Added a `frontend` job.

Honest about what the e2e step gates: the spec skips itself when no backend
is reachable, and CI starts none, so it verifies the app builds and serves.
Running the real journey in CI needs Postgres, a seeded KB and provider
config — its own piece of work, not smuggled into a hygiene phase.

### Known, untouched: `black --check` is already red

Seven files fail formatting on clean HEAD, none of them touched by this
work (stability model/router/templating, seed demo test, two older
migrations). Almost certainly drift from the unpinned `black>=24.0`. Left
alone so this phase's commit stays scoped; it needs its own call —
reformat, or pin black to the version the code was written against.

---

## P24 — Derived documents, and closing the target (2026-09-10)

**Platform capability: 55/98 → 98/98 leaves, and `--strict` is now the CI
gate.** Twenty-one sections registered, three derived-document modules
added, one numbering drift fixed, two open regulatory questions answered,
and a worked example that builds the whole dossier end to end.

The phase's real deliverable is not the sections. It is that the target
stopped being a progress bar and became a contract CI enforces — and,
below, the record of **everything the 98-leaf target got wrong**, because
that file is what every future submission type will be derived from.

### What the target got wrong

Written first because it is the part worth re-reading. None of these was
visible while the target lived in prose; each surfaced only once a machine
compared the contract against the platform.

**1. A leaf was filed at a heading's number, for eight phases.** The
registry registered the registration form as `"1.2"` from P04. In the
target — derived leaf by leaf from a real filed dossier — 1.2 is a
*heading* and the document is 1.2.2. Nothing rendered wrongly, nothing
failed, and no test noticed: the number is just a string until something
compares it to a contract. Renumbering was not free (the instance key, the
leaf filename, the storage key, the narrative lookup and rule R26's
`section` pointer all contain it), and it was done rather than annotated,
because a permanent asterisk in the contract poisons everything derived
from it later.

**2. `production` is single-valued, and three leaves produce two
documents.** 3.3, 5.4 and 5.3.1.2 each ship an *uploaded* artifact and a
*generated* companion — the literature pack plus its reference list, the
CRO's study report plus a structured summary. The YAML can only say one
thing per leaf, so it says `uploaded` and the generated half is invisible
to the contract. The platform handles it (`SectionSpec.leaf_suffix`, from
P22), but the target cannot express it. **A future schema_version should
make `production` a list.**

**3. `production: uploaded` conflates two different situations.** For a
CPP the file *is* the leaf and nothing else belongs there. For 3.3 the file
is *evidence* filed under a heading that also carries our own content.
Same declared production type, opposite meanings for assembly.

**4. A leaf number is not a document count.** 98 leaves produce **102 leaf
PDFs** for the worked example: 3.2.P.4.1 repeats per excipient (four),
3.2.P.3.1 per manufacturing site (two), 3.2.P.7 per pack (two), and the
three leaves in point 2 file two documents each. Anyone reading "98" as
"98 files" will write a test that fails on the first combination product.

**5. `blocked_by` capabilities have no way to say they have landed.** The
check printed them under "build these first", which stopped being true
when the last one landed. Fixed by computing whether any leaf citing a
capability is *still* a gap and printing `landed` / `OUTSTANDING`. The
`blocked_by` entries themselves stay — they are the dependency map that
made the build order legible, not a to-do list that deletes itself.

**6. The contract implies every leaf is a registry section. Four are
not.** A `production: toc` leaf cannot be: `render_section` is handed a
Project, and a table of contents is a function of the *package*, which does
not exist until every other leaf has been rendered and placed. They are
built in `ctd/toc.py` and the check imports `MODULE_TOC_LEAVES` to credit
them, rather than a second list of four numbers that could drift.

**7. 1.2.6 is two documents under one heading.** "Power of Attorney /
Contract Manufacturing Agreement" — the platform can author the first and
never the second (an executed agreement between two companies is not ours
to write). The target's own note flagged it; it is still unsplit, and the
GMP compliance undertaking is what lands there today.

**8. Three leaves had no identity in the built package.** 1.2.4, 1.2.5 and
1.2.6 rendered and were placed correctly — and were *named*
`power-of-attorney-<uuid>.pdf`, so an assessor working down the table of
contents had to open three files to find one leaf. Found by the end-to-end
reconciliation asking the reverse of the usual question: not "does every
leaf have a document" but **"does every document name its leaf"**. Worth
keeping as a technique.

### The two open regulatory questions

**1.2.1 "Application form" vs 1.2.2 "Registration form" — build both.**
Not confirmed against NAFDAC's current form set, and the reasoning matters
more than the answer: the cost of the two errors is wildly asymmetric.
Filing two documents where the agency wanted one is a redundant page;
filing one where it wanted two is a deficiency letter. Both render from the
same applicant, product and project records through one dispatch branch, so
the redundancy carries no risk of contradiction — which is the only thing
that makes duplication acceptable. If it turns out to be one document,
delete the leaf and its slot; nothing else changes.

**1.6 "Samples" — a record of what was sent.** Confirmed from the leaf's
own nature rather than from guidance: samples are physical, and a folder
cannot hold a tablet. What the dossier owes there is a statement tying the
samples arriving at the agency's laboratory to the batches the dossier
files — so the batch numbers are the same rows 3.2.P.5.4 files, and a
sample cannot be presented under a batch number the submission never
described. The exact form NAFDAC expects is still unconfirmed, but that is
presentation, not structure.

### The derived documents, and the one mechanism behind them

`app/templating/derived.py` renders the context dicts Module 3 itself
renders from and returns them keyed by instance. The QIS (1.4.2) and the
QOS (2.3) read their values out of *those*. Neither is ever handed a
model, so there is nothing to re-query: `field()` raises when a context has
no such key and `context_for()` raises when a section was not rendered, so
a derived field with no Module 3 source fails at build time instead of
rendering a blank somebody has to notice.

The property this buys is worth stating precisely, because it is the defect
the whole platform exists to remove. 3.2.P.8.1 refuses to print a claimed
shelf life the long-term data do not reach — it prints a marker naming both
figures. Because the QIS field and the QOS's 2.3.P.8 line *are that same
string*, an unsupported shelf life is now **unprintable in the summary**,
not merely blocked at export. A QIS with its own `shelf_life_months` lookup
would print it happily, on the first page an assessor reads.

Eighteen tests hold it by mutation: change a fact in Module 3, assert both
documents follow. A field that did not follow would have its own copy of it,
whatever the code looked like.

One structural note: `derived.py` imports `build_context` *inside* the
function. The cycle is real rather than accidental — a derived document is
built from other sections' contexts, but reaches them through the same
dispatcher every section goes through — and the honest place to break it is
the higher layer.

### 3.3's reference list, which turned out to be the interesting one

A Module 3 bibliography is the monographs and ICH guidelines the quality
case rests on, and the dossier already says which those are, in three
places nobody thinks of as a bibliography: every specification row's
`method`, every impurity's `limit_source`, every material's
`compendial_std`. So 3.3 cannot cite a standard the dossier does not rely
on, nor omit one it does.

First version printed those strings verbatim and produced a list whose
reference 4 was "GC, ICH Q3C" — a *method*, not a citation. Now the
standard is extracted ("HPLC, BP monograph" → BP). The line being walked:
recognising the token "ICH Q3C" in a string is reading what the filer
wrote; splitting "Smith et al., J Pharm Sci 2019;108:1123" into authors,
journal and year would be inferring a structure they never entered, and a
citation pointing subtly elsewhere is worse than one passed through
untouched. So 5.4's entries are printed exactly as typed.

Monographs are **cited and never reproduced** — the same line
`knowledge/ingest.py` holds for the KB, and the reason a reference list is
the copyright-safe way to point at a pharmacopoeia at all.

### Turning the gate on, and the semantic call it forced

`--strict` in CI needed one decision: **is a placeholder a gap?**

It depends on the question, and the check now has two scopes. Without
`--project` it asks whether the *platform* can produce or place every leaf,
and a placeholder passes — placing the file is everything the platform can
do about a regulator's certificate, and failing CI because nobody has
attached a CPP to a hypothetical project would be a red build no commit
could turn green. With `--project` it asks whether a *filing* is complete,
and there a placeholder is exactly the gap.

`resolve_status` was left alone, so the report still prints 22 leaves as
placeholders and P18's careful distinction survives intact. What changed is
only what *fails the build*.

Project scope then needed a third state. A conditional leaf the filer
answered "no" to is not missing paper — it is a scoping **answer**. Without
`not_owed_keys`, no correct filing could ever reach 98/98, and worse, the
number would have pushed a filer to attach *something* at a leaf they had
already declared out of scope. It reads the same `resolve_applicability` the
builders read, so the check cannot disagree with the package about what the
filing owes.

### The worked example, and what the fixtures caught

`app/seed/amlodipine.py` — AMLOVEX 5 mg tablets, a complete defect-free
filing, seeded under this project's own fictional company. The target was
*derived from* another company's dossier (a leaf list is not confidential);
copying their specification, batch numbers and stability data would have
been a different thing entirely.

It builds: **102 leaf PDFs covering 93 of the 98 target leaves**, the other
five scoped out by the filer's own conditional answers (no biowaiver, no
previous marketing authorization, no BA-only study, no excipient method
validation). Four module TOCs, a package TOC, and an eCTD backbone that
passes the DTD and the mechanical checks.

Three things the platform caught in its own fixture, which is the strongest
evidence the rules work:

- **Amoxicillin's water in amlodipine's specification.** The shared
  substance tables report ~13 % water — amoxicillin *trihydrate*'s water of
  crystallisation. Amlodipine besilate's own limit is NMT 0.5 %, so R22
  rejected every batch result and R05 refused the retest period. The
  fixture was wrong; the rules said so.
- **A penicillin SmPC on a calcium-channel blocker.** Reusing the shared
  clinical particulars would have warned an amlodipine patient about
  penicillin allergy. Not a cosmetic fixture problem: a worked example whose
  own particulars are for a different drug class undercuts the entire
  demonstration on the first page a pharmacist reads. Hence
  `ClassParticulars`.
- **A NAFDAC-only leaf in an EU package.** 1.2.1, 1.2.14 and 1.6 were
  registered without `only_when_applicable`, and building the same dossier
  as an EU sequence raised on a Module 1 number the EU profile has no slot
  for — `folder_for_section` refusing to guess, exactly as designed. P22
  built that flag for this case and its comment says so; the leaves simply
  did not use it.

And one ordinary bug worth recording for how it announced itself: the
3.2.P.2.2 overage column reported **−12.9 %** for a line with no overage at
all. `BatchFormulaLine.qty_per_unit_mg` holds the *base* quantity — R04
multiplies by the salt factor itself — so the arithmetic was comparing
500 mg of base against 574 mg of trihydrate and calling the difference a
formulation decision. Overage is base against base. It was visible only
because the section was rendered and read, not because a test failed.

Also: a project committed with an empty `sections` collection raises
`MissingGreenlet` the moment a rule touches it under the async engine.
Every previous seed happened to append a Section; the first that did not,
found it.

### Known gaps

- **No rule blocks the export when a non-certificate uploaded leaf is
  simply absent.** R20 covers certificates (it generated the placeholder,
  so it knows). A filing with nothing attached at 3.2.P.5.3 builds a
  package quietly missing that leaf. `--project` strict reports it; the
  export gate does not. That asymmetry should close.
- 1.2.6 is still two documents under one heading (point 7 above).
- `confirmed_against_guideline` in the target is still `null`. Every
  regulatory fact in this repo is re-confirmable from one file, and none of
  it has been re-confirmed against NAFDAC's *current* published guideline.
  That is the single largest caveat on the number 98.

---

## P23 — Product information: one dataset, three audiences (2026-09-08)

**Platform capability: 52/98 → 55/98 leaves.** Three sections registered
(1.3.1 SmPC, 1.3.2 labelling, 1.3.3 patient leaflet), one table added, six
rules added, one new narrative register, and one real gap closed in the EU
regional backbone.

### What was actually wrong

Nothing, in the sense that no code was broken. The problem was that the
three documents did not exist, and the reason they could not exist is the
interesting part.

The Summary of Product Characteristics, the outer and inner labels, and the
patient information leaflet say the same things to three audiences. They
must agree on strength, shelf life, storage, pack sizes, indications and
contraindications. In real filings they routinely do not — they are written
at different times by different people, and a shelf-life extension updates
two of the three. It is one of the most commonly raised deficiencies there
is, and it is **not caused by disagreement**. Nobody disputes the shelf
life. There are simply three copies of it.

That framing decided the whole phase.

### The mechanism: derive, do not re-enter

`app/templating/product_information.py` has one function,
`shared_values(product)`, which computes every fact appearing in more than
one of the three documents: the product name, strength, dosage form, route,
excipient list, shelf life, storage condition, container contents and legal
status. All three context builders read it. Nothing else recomputes any of
them, and **no column anywhere stores a second copy**.

So the failure mode is not caught. It is unproducible.

`ProductInformation` (the new table) therefore holds only what the
documents ADD: the SmPC's clinical particulars, 4.1–4.9 plus 6.2 and 6.6,
one column per numbered section. It has no `shelf_life_months`, no
`storage_condition`, no `strength`, no `pack_size`. A test asserts those
columns are absent, because the absence is the design — adding one would
restore the defect in a single migration, and the platform would then need
a rule to catch what it had just finished making impossible.

### Three layers saying the same thing

The interesting design work was making that refusal *legible* rather than
merely true:

- **Model**: no column, so a second copy is unstorable.
- **API**: `ProductInformationWrite` sets `extra="forbid"`, so a PUT naming
  `shelf_life_months` gets a 422 naming the field. Pydantic's default —
  ignoring unknown keys — is the worst of the three options: the write
  appears to succeed, the value vanishes, and the filer believes the SmPC
  now says 36 months.
- **UI**: the derived values are shown, read-only, each with a
  `source` sentence naming where it comes from ("Claimed on the product;
  your long-term stability data supports 24 months"). Not a disabled
  `<input>` — a greyed box still reads as "a field you may not use right
  now", and the filer's next move is to look for the permission. Rendering
  it as text with provenance says something different: this is not a field,
  it lives over there.

An SmPC page that simply *omitted* section 6.3 would have been the obvious
shortcut and would have been much worse — a pharmacist would assume the
platform had forgotten it.

### Where the LLM is and is not allowed

**The clinical particulars are DATA, not narrative slots.** A therapeutic
indication is a regulatory claim; so is a contraindication and so is a
dose. A model that drafts "also indicated in paediatric patients" has
invented a marketing authorisation, and the existing guardrails cannot
catch it — there is no number to leak and no citation to fabricate. This is
the clearest case yet for AGENTS.md §5's determinism boundary: an
indication is the most cross-checked value in Module 1.

The slots that DO exist are the SmPC's 5.x sections (pharmacodynamic,
pharmacokinetic, preclinical — literature-derived description, which is
what the knowledge base is for) and the leaflet's four patient-facing
headings. The label has none at all, which after 1.4.1 is the platform's
second-strongest case for a fully generated document.

### The leaflet register — a distinct slot type, not a different prompt

The prompt asked for this explicitly and it was the right call to insist
on. `SectionSpec.narrative_register` declares 1.3.3 as `PATIENT`, which
selects both a different system prompt **and** a different output check
(`check_patient_register`): a jargon translation table
(contraindicated → must not be used, hepatic → liver, concomitant → at the
same time), a 25-word sentence limit, and whether the text addresses the
reader as "you".

WHY the check and not just the prompt: **a prompt is an instruction a model
may ignore silently, and nothing downstream would know.** The register has
to be checkable on the output. Rule R33 re-runs the same check on APPROVED
text at export, which is where it becomes a gate rather than advice.

WHY a readability *index* was rejected: Flesch-Kincaid counts syllables, so
it scores "paracetamol" as hard and "may cause death" as easy — and it
cannot tell a filer what to change. The jargon table names the term and the
plain alternative, which is the difference between a measurement and a
correction.

R33 is a WARNING, not an ERROR. Jargon in a leaflet is a readability
failure, not a false statement; blocking on it would put the platform in
the position of refusing to export a filing over a word choice a competent
regulatory writer may have made deliberately.

### The six rules, and what each one can actually catch

The three documents cannot disagree with each other, so most of the rules
are about the relationship between the product information and the REST of
the dossier — which is where divergence remains genuinely representable:

- **R28 — excipients vs the batch formula, both directions. ERROR.** SmPC
  6.1 and the leaflet render from `product.excipients`; 3.2.P.3.2 is what
  is actually weighed. Separate tables, entered at different times, and
  they drift. A patient with an intolerance reads the leaflet, which is why
  this blocks rather than warns.
- **R29 — the label's storage temperature vs the long-term study's. ERROR.**
  The climatic-zone defect: Zone II tests at 25 °C, Zone IVb (Nigeria) at
  30 °C, and a dossier assembled from a European parent filing arrives with
  25 °C data and a label rewritten for the Nigerian market. Five degrees
  nobody typed on purpose. Parses a temperature out of both free-text
  fields and is silent when it cannot find one on either side.
- **R30 — the authored sections are authored.** ERROR on 4.1/4.2/4.3
  (those three ARE the application — without them there is nothing to
  approve), WARNING on the rest, because "no interactions are known" and
  "nobody filled this in" are different statements and only one is a filing.
- **R31 — the three documents agree. ERROR, and it cannot fire today.**
  A deliberate regression tripwire: it asks the three *rendered contexts*
  what each will print, rather than asking `shared_values` once (which
  would be a check that a value equals itself). The regression it waits for
  is specific and likely — someone adds a column "just for the label". A
  test forces exactly that divergence and asserts R31 catches it, so the
  guard has been seen to fire.
- **R32 — the leaflet's prose carries every contraindication. WARNING.**
  The *list* is printed verbatim either way; that guarantee is in the
  template. What this checks is the drafted prose above it, where a
  paraphrase loses one.
- **R33 — the register gate** (above).

### The bug worth writing down: an empty stopword list is not a stopword list

R32 was written with a stopword list of ordinary grammar words ("a", "the",
"in", …) and a rule that one shared content word means the contraindication
survived the paraphrase. It passed nothing.

The contraindication *"You have ever had jaundice or a liver problem after
taking this medicine before"* was satisfied by leaflet prose reading *"Do
not take this medicine if you are allergic to penicillins"* — because both
contain the word **"medicine"**.

The second class of stopword is the vocabulary every leaflet is *made of*:
medicine, take, taking, doctor, problem, ever, before, you, your. Strip
both classes and what remains is the clinically distinctive word — the
organ, the condition, the drug class — which is the word a paraphrase has
to keep in order to still be saying the same thing. The failing test named
the wrong contraindication, not the wrong mechanism, which is what made it
take a moment to see.

### The second bug: `updated_at` is not covered by expire_on_commit=False

The PUT worked on create and failed on update, with `MissingGreenlet`
raised inside Pydantic's serialisation of `updated_at`.

`Base.updated_at` carries `onupdate=func.now()`, so SQLAlchemy marks it
stale after an UPDATE **regardless of `expire_on_commit=False`** — the next
read of it is IO, and on the async engine that is a crash rather than a
blocking call. An INSERT's server defaults come back with the row, so
create-then-read looked perfectly healthy while update-then-read did not.
One `await db.refresh(...)` after the commit; the reasoning is in the route
so nobody removes it as redundant.

### The third bug: a test flake that fails in the wrong test

`test_none_of_the_three_can_be_made_to_disagree` failed roughly one run in
three, and never on the assertion it was making. It died inside
`run_all(project)` — specifically inside rule **R15**, reading
`project.declarations`, with a `DetachedInstanceError`.

The `_load` helper this repo's model tests all share builds a project,
commits it to a throwaway SQLite database, and returns it:

```python
session = Session(engine, expire_on_commit=False)
session.add(project); session.commit(); session.refresh(project)
return project
```

`session.refresh()` expires **every** attribute, relationships included —
so a rule walking `project.declarations` later triggers a lazy load, and a
lazy load needs the Session. Nothing holds a strong reference to it after
`_load` returns; SQLAlchemy's instance state references it weakly. So the
test passes or fails depending on **whether the garbage collector got there
first**, which is why it was intermittent and why it surfaced in whichever
test happened to run after the collection.

Pinning the session to the returned object (`project._test_session =
session`) fixes it.

The same helper is copy-pasted into **eleven other test files** (grep
`session.refresh(project)`), all carrying the same latent hazard. They are
deliberately left alone: none has been observed to fail, and rewriting
eleven other phases' fixtures inside P23 is exactly the silent scope creep
this log exists to catch. Recorded here so the next person who sees a
`DetachedInstanceError` in an unrelated rule does not spend an afternoon on
it — the bug is never in the test that reports it.

### A real gap closed: `m1-3-pi` in the EU backbone

Unlike 1.4.1, these three leaves are `applicable: true` — they are emitted
for every project, in every region. So an EU project would have reached
`folder_for_section_instance` with no folder and raised at build time.

Adding EU Module 1 slots fixes placement, but on its own would have
produced three files in the package that the regional XML never mentions —
the exact "looks complete, is not" failure this platform exists to prevent.

The DTD turned out to hand us the answer. `eu-regional.dtd` declares
`m1-3-pi` containing `m1-3-1-spc-label-pl (pi-doc+)`, and `pi-doc` carries
a **#REQUIRED `type`** attribute from
`(spc|annex2|outer|interpack|impack|other|pl|combined)`. The EU spec names
these three documents itself and insists you say which is which, because an
assessor's software routes on that attribute. So: SmPC → `spc`, labelling →
`outer`, leaflet → `pl`. (`combined` means all three filed as ONE document
— precisely the practice this phase makes unnecessary.)

Ordering matters and cost a moment: `m1-eu`'s children are declared in a
fixed order, lxml appends in call order, and a `pi-doc` appended before
`m1-2-form` fails DTD validation with a message about content models rather
than about order. The elements are therefore built detached and attached at
the end.

### Fixture change worth noting

Every seed's batch formula listed only its ACTIVE lines. A batch formula
that lists only the actives is not a batch formula — and nothing said so
until R28 existed. All three fixtures now carry their excipient lines, and
AMPICLOX's buggy variant plants the phase's defect: a glidant (colloidal
silicon dioxide) in the batch formula with no excipient row, so it is
manufactured into every capsule and named in neither SmPC 6.1 nor the
leaflet.

Note **how** the fixture has to plant it. There is no field anywhere that
could hold a divergent excipient list, so even a seed deliberately trying
to create this defect has to create a genuine disagreement between two real
tables. That constraint is the phase, stated from the inside.

### Scope calls

- **The documents print the CLAIMED shelf life, not the supported one.**
  3.2.P.8.1 prints what the data supports because it is an argument ABOUT
  the data; a label is a statement of what was authorised, and one silently
  printing a shorter period would file a shelf life nobody applied for. So
  the claim is printed, R05 blocks when the data does not reach it, and the
  provenance line shows both numbers at once.
- **Batch number, manufacturing date and expiry are left blank on the
  label**, marked as overprinted at packing. They are per-batch facts; a
  dossier that filled them in would file one batch's label as the artwork
  for all of them.
- **One document for both labels.** The target TOC's leaf says "outer and
  inner labels", and the two differ in what they FIT, not in what they say
  — the inner renders as a subset of the same values.
- **JSON columns for the three list sections**, not child tables. Same call
  and same reasoning as `Project.condition_answers`: always read and written
  as a whole, nothing points at an individual entry. What would change our
  mind is recorded: the day a side effect must link to the
  pharmacovigilance signal that found it, an entry needs an identity and
  earns a table.

### What this leaves for later

The comparison screen currently always reports zero divergences, and that
IS the demonstration — but it means the screen's most striking state is one
a user cannot reach with their own data. A demo mode that shows the
divergent version side by side would make the argument land harder for
someone seeing the platform for the first time.

---

## P22 — Bioequivalence as data (2026-09-07)

**Platform capability: 48/98 → 52/98 leaves.** Four sections registered
(1.4.1, 5.2, 1.2.17, 1.2.18), a fifth rendered as a companion leaf at
5.3.1.2, four tables added, three rules added and one rewritten.

The phase brief predicted five. It landed four, and the missing one is not
a shortfall — it is the check refusing to be fooled, which is worth more
than the number. See "Why the count is four and not five" below.

### What was actually wrong

`ClinicalEntry` was `kind` + `reference_product` + a free-text `summary`,
hanging off the Product. Rule R06 could therefore check exactly one thing:
that a row existed.

For a multisource filing that is the weakest place in the whole platform.
Everything in Module 3 establishes that the product is made consistently
and to a specification. Only leaf **5.3.1.2** establishes that it works —
it carries the entire scientific argument for approval, and the question
it answers is arithmetic: does the 90 % confidence interval of the
test/reference ratio of Cmax and AUC fall inside the accepted window?
Nothing could ask that. Nothing could check that the comparator named in
the study was the one named on the application form. And **leaf 1.4.1, the
Bioequivalence Trial Information form, is generated entirely from study
data**, so it could not exist at all — a Module 1 document that a filer
had to retype out of a Module 5 PDF, which is precisely the work this
platform exists to delete.

### What replaced it

Four tables, and the split between them is the design.

**`ReferenceProduct` is a reference, not a string.** The comparator has an
identity (brand, strength, manufacturer, country of origin) and a physical
instance (the batch bought, and its expiry). An assessor checks that the
batch was in date when it was dosed and that the brand is the one the
application claims equivalence to; neither is checkable against a
sentence. It hangs off the Product rather than off the study because a
fasting study and a fed study routinely dose the same comparator batch,
and re-entering it per study is re-entering it wrongly once.

**`BioequivalenceStudy`** carries the design, the conduct, and two
foreign keys that are the whole point: the comparator, and the test batch
— a real key to the batch whose analysis 3.2.P.5.4 already files, for the
same reason `StabilityStudy` points at one. An assessor cross-references
that batch number between Module 5 and Module 3, and a string would let
the two sections name different material with nothing to notice.

**`BioequivalenceResult`** is one row per pharmacokinetic parameter, each
with its geometric mean ratio and both bounds of its 90 % CI. One row per
parameter rather than six columns on the study, because the verdict is per
parameter: R25's finding has to name Cmax and the bound that failed, not
"the study". `Numeric(7, 2)`, never `float` — the window is written to two
decimals, and a rounding artefact here decides a marketing authorisation.

**`Biowaiver`** is the other route: a BCS-based or additional-strength
request, which is what 1.2.17 and 1.2.18 are rendered from.

### The claim and the evidence, kept apart deliberately

`Product.reference_product_name` / `.reference_product_manufacturer` are
what the APPLICATION declares — the comparator printed on the registration
form (1.2) and in the QOS (2.3). The `ReferenceProduct` row is what the
STUDY actually dosed. They are stored separately, and rule R26 reconciles
them.

That looks like duplication and is the opposite of it. It is exactly the
shape `Product.shelf_life_months` already has against the stability data:
the claim lives on the product, the evidence lives in the data, and a rule
refuses to let them disagree. Collapse the two into one field and R26
becomes a check that a value equals itself — while the real filing error
stays perfectly possible in the paperwork. The error is ordinary, not
exotic: the comparator originally planned is not the one the CRO could
source, the study runs against what was bought, and Module 1 still names
the original. AMPICLOX's buggy fixture plants exactly that.

### Where the acceptance window lives, and why it is configuration

In `app/ctd/region_profiles.py`, beside the Module 1 slots and the
applicability table — **not in R25's body**, which the brief was explicit
about and which is right for reasons worth stating.

It is a regulatory parameter and every property of one applies: it is
written into guidance rather than derived, agencies do not all state the
same one, and it moves. A rule with `80.0` typed into it is a rule that
has to be edited, re-reviewed and re-tested when an agency republishes a
table — and the person who knows the guidance changed is not the person
who reads Python. This file already exists to be the place a regulatory
fact is re-confirmable by someone reading ONE file.

Two windows, because there are two: 80.00–125.00 % ordinarily, and
90.00–111.11 % for a narrow-therapeutic-index drug, where a 20 % swing in
exposure to warfarin or levothyroxine is a clinically different dose.
Both are asymmetric because they are symmetric on the log scale, where the
statistics are done (1/1.25 = 0.80).

**Which window applies is a property of the MOLECULE, not the region.** So
the region owns the pair and the product owns the flag
(`Product.narrow_therapeutic_index`), joined by one function,
`RegionProfile.window_for(product)`. The rule that CHECKS the interval and
the BTI form that PRINTS the window call that same function — the same
discipline `supported_months` enforces between 3.2.P.8.1 and R05, and for
the same reason: a form stating a criterion the gate does not apply is the
contradiction class this project exists to remove.

`TestBatchRule` sits beside it for R27, holding WHO TRS 992 Annex 7's two
numbers (a tenth of the commercial batch, or 100 000 units, whichever is
greater).

### The rules

- **R25** — a 90 % CI outside the window. ERROR; names the parameter and
  the bound, because a low lower bound and a high upper bound are
  different problems with the same product.
- **R26** — the study's comparator against the one the application
  declares. The cross-module check the platform was built for. The
  comparison folds case, spacing and punctuation away ENTIRELY — "Amoxil
  500mg Capsules" and "Amoxil 500 mg capsules" are one product typed by
  two people, and a rule that reported them as two comparators would fire
  on every filing and be switched off. It still separates Amoxil from
  Ospamox, and 250 mg from 500 mg. (The first version collapsed runs of
  punctuation to a single space rather than removing it, which read
  "500mg" and "500 mg" as different products; the test caught it.)
- **R27** — the test batch against the commercial batch in 3.2.P.3.2. A
  genuine regulatory finding that exists only in the space BETWEEN two
  modules: the biobatch size is in Module 5, the commercial batch size is
  in Module 3, and nobody reading either alone can see the problem.
- **R06** — rewritten, not duplicated. From "a bioequivalence row exists"
  to "**exactly one route is filed**": neither an in vivo study nor a
  biowaiver is an incomplete dossier, and both is a contradiction — the
  application saying at once that a human study was necessary and that it
  was not. It also stopped firing on new chemical entities, which was
  wrong in a way nothing had noticed because nothing had built an NCE
  filing yet.

R06 reads the biowaiver claim from the **applicability answers**, not from
the `Biowaiver` row. That is deliberate: P17's answer is what makes the
leaf applicable and therefore what puts the request in the package, so it
is the thing that has to be checked. Reading the row instead would let the
row exist while the leaf stayed out of the dossier — a filing where the
platform believes a claim the regulator never sees.

### Two new registry capabilities, both forced by real leaves

**`SectionSpec.only_when_applicable`** — emit a section only for a project
whose applicability says it applies. It is `is_statement`'s mirror (that
one emits when a section does NOT apply) and both read the same
resolution. This is what makes the biowaiver decision real: answering
"yes" to 1.2.17 is not a preference recorded somewhere, it is a document
appearing in Module 1. It also keeps a NAFDAC-only Module 1 leaf out of an
EU package — the EU applicability table is empty, meaning "not modelled",
so nothing is claimed and nothing is emitted, rather than the eCTD builder
raising on a leaf it has no folder for.

**`SectionSpec.leaf_suffix`** — a rendered document that ACCOMPANIES an
uploaded one at the same section. This one was forced by a trap worth
recording. Assembly keys leaves by instance key, and **an uploaded file
wins over a rendered one at the same key** — which is correct, because a
generated stand-in for a signed certificate is not an improvement on the
certificate. 5.3.1.2 is the case where it is wrong: the CRO's report and a
structured summary of the study data are two different documents that both
belong under that heading, and the eCTD DTD agrees (`m5-3-1-2-…` has a
`leaf*` content model). Without the suffix the summary would have been
silently deleted the moment the report was attached — "looks complete, is
not", which is the exact failure the platform exists to prevent, arriving
through the mechanism built to prevent it.

### Why the count is four and not five

The brief expected five leaves, one per `blocked_by: [be_study_model]`
entry. Four moved. **5.3.1.2 did not, and it should not have.**

It is an `uploaded` leaf, and `resolve_status` credits one as done only
when a real file has actually been attached in a real project. The
platform can now render a structured summary there, and crediting the
section because of that would be laundering the single most important gap
in a multisource dossier into a green tick — the precise move
`check_target_toc.py`'s docstring says it exists to refuse. So the leaf
stays a placeholder in platform mode and goes to `done` in `--project`
mode once the report is in, which the seeds now attach.

The alternative — reclassifying it as `hybrid` to make the number move —
was considered and rejected in about ten seconds. A contract that can be
edited to report progress is not a contract.

### THE SCALE FINDING: a filing cannot span strengths

Recorded either way, as the brief asked, and the answer is the
uncomfortable one.

**`Project` → one `Product` → strength on its `ActiveIngredient` rows.**
There is no product family. A filing covers one strength.

Leaf 1.2.18 is "biowaiver request for an ADDITIONAL strength", and it
presumes exactly the span the model does not have. Amlodipine — the
dossier this whole target TOC was derived from — files at 5 mg and 10 mg.

What was built: the leaf is reachable. The request renders, names the
strength it covers, and cites the in vivo study it leans on by foreign
key. What was not built, and cannot be: `Biowaiver.strength` is a plain
STRING, and the proportionality checks the leaf actually wants
(proportional composition, comparable dissolution against the strength
that WAS studied) are impossible, because the other strength is not in the
filing at all.

Rather than only writing that down, it is asserted:
`test_a_biowaiver_records_its_strength_as_text_because_a_filing_is_one_strength`
fails the day `Product` grows a family, and points whoever is holding it
at the leaf that was waiting. The field's own comment says the same thing
where the next person will read it.

Naming it now was the cheap moment. It will resurface — a real generic
company files a strength range as one application, and the day that lands,
`Product` needs a family, `Project` needs to point at it, and every
per-strength section needs a repeat axis it does not have.

### MissingGreenlet, a fourth time, from a fourth direction

Sixteen tests failed on `build_ctd_package`, deep inside R06, nowhere near
a query. The cause was `product.biowaivers`.

The pattern is now unmistakable and the new instance is instructive.
P18 recorded it for `Project.documents`; P20 for a batch's results; P21
for a nested `*Read` field. Here it was a collection **the seeds never
touch** — and every other collection on `Product` escapes the trap only by
accident, because the seeds happen to append to all of them and appending
marks a collection loaded.

`biowaivers` is the first collection a COMPLETE filing legitimately leaves
empty: a filing that ran an in vivo study claims no biowaiver. So it is
the first one to fail. The fix is the one `Project.__init__` already
documents — start the collection loaded and empty at construction — and
the generalisable lesson is sharper than "eager-load your reads": **a
collection that a valid object may legitimately never populate cannot be
left to lazy loading, because nothing in the fixtures will ever load it
for you.**

### Deviations and costs, recorded rather than waved past

- **A second custom wizard editor.** P21's build log said its grid was
  "worth making exactly once… not a licence to hand-write the next
  screen". This is the second, and the justification is different rather
  than borrowed: the comparator is a row other rows point at (a text field
  would put back the drift R26 exists to catch), and the results are a
  fixed three-parameter table saved as a set. A test now pins the
  exception at exactly two editors, so a third has to argue for itself by
  failing it.
- **A third place validation is drawn** (`src/lib/be-window.ts`),
  mitigated as the other two are: advisory only, R25 is the gate, and the
  window is passed in rather than hard-coded — this module knows how to
  compare, not what the limit is.
- **The test suite got slower.** Every project now renders three more
  leaves, each through a fresh headless LibreOffice. That is the honest
  cost of a phase whose deliverable is documents; the fix, if it is ever
  wanted, is a persistent soffice process rather than fewer sections.
- **The free-text `ClinicalEntry` bioequivalence row was not converted.**
  It could not be — the row holds a sentence, and a sentence does not
  contain a study design, a subject count or a confidence interval.
  Manufacturing those to fill a table would be putting invented regulatory
  data in front of an assessor with the platform's authority behind it.
  The migration copies the one fact the row does hold (the comparator
  name) onto the product, leaves the row alone, and R06 stops accepting it
  as evidence. Every pre-P22 project now reports "no bioequivalence
  route", which is an accurate statement about a dossier whose central
  document is a paragraph.

---

## P21 — Stability as data, not a paragraph (2026-09-07)

**Platform capability: 43/98 → 48/98 leaves.** Six sections registered
(3.2.S.7.1/.2/.3 and 3.2.P.8.1/.2/.3), one existing section rewired, and a
validation rule upgraded from arithmetic about the wrong thing into a real
out-of-specification check.

The phase brief predicted four new leaves. It landed five, because
3.2.S.7.1 turned out never to have been registered at all — only the drug
PRODUCT's summary existed, since a stability study could not belong to a
substance. The sixth section, 3.2.P.8.1, already counted as done and was
rebuilt underneath rather than added.

### What was actually wrong

`StabilityStudy` carried `study_type`, `condition`, `duration_months`,
`protocol` and a free-text `result_summary`, hanging off the Product.
Three separate defects, and each of them was a section the dossier owes:

1. **Drug-product only.** 3.2.S.7 is the drug substance's stability, filed
   per substance. One `product_id` could only ever answer 3.2.P.8, so a
   combination product's two actives had nowhere to put their data.
2. **The study's real axes were flattened.** A stability study is run on a
   named BATCH, at a storage CONDITION, in a specific PACK PRESENTATION.
   3.2.P.8.3's tables are organised along exactly those axes — an assessor
   reads "batch X, 30C/65%RH, blister" as one column — and a model
   carrying only the condition cannot produce them.
3. **The results were prose.** "Within specification through 24 months"
   cannot be rendered as the timepoint × test table the section IS, and —
   the part that matters — cannot be checked. It can say "within
   specification" while dissolution at 12 months was 68 % against an
   NLT 80 % limit, and nothing in the platform would know.

### The axes, which are the part hardest to change later

The owner is the same two-owner polymorphism `BatchAnalysis` uses
(`app/models/spec_owner.py`): a study is a study OF the drug substance or
OF the finished product, and the CTD has no third place to file one.

The batch is a **foreign key to `BatchAnalysis`**, not a re-typed batch
number. ICH Q1A(R2) asks for stability data on the same primary batches
whose analysis is filed in 3.2.S.4.4 / 3.2.P.5.4, and an assessor
cross-references those numbers between the two sections. A string would let
the two sections name different batches with nothing to notice.

The pack is a foreign key to `Packaging`, because "in the container closure
system proposed for marketing" is a requirement rather than a detail — a
shelf life supported in a drum does not support a blister.

`result_summary` was **renamed to `notes`, not dropped**. The migration will
not throw away a filer's text, but the text stops being the section's
answer: 3.2.S.7.1 and 3.2.P.8.1 are now built from the timepoint results.

### The deviation from the brief, stated plainly

The brief asks the result model to carry "whether it meets the criterion".
It does — as a **derived property, not a stored column**. A stored boolean
is a second copy of a judgement the acceptance criterion already
determines, and the two can disagree: edit the limit and the stored verdict
is silently stale, which is exactly the failure the foreign key one level
down exists to prevent. Deriving it costs a regex per read and makes the
disagreement unrepresentable.

### The rule that justifies the whole phase

R23 (`stability_results_within_specification`) is R22's sibling: the limit
is reached through `result.specification_test`, never copied. Tighten a
limit in 3.2.P.5.1 and every timepoint already on file is re-judged with
nothing re-entered — there is a test for exactly that.

R05 was upgraded, and the upgrade exposed **two latent bugs that had been
there since P06**:

- It compared the claim against `duration_months` — how long the study
  RAN. A 24-month study that failed dissolution at 6 months read as 24
  months of support. The arithmetic was right and the question was wrong.
- Its `max()` ran over *every* study on file, so a six-month accelerated
  study counted as six months of shelf-life support. It does not:
  accelerated conditions detect significant change and support
  extrapolation, never the shelf life itself. R24 now says so separately,
  as a WARNING — R05 gates on the arithmetic, R24 surfaces a judgement
  about study design, and a rule that is inferring should not gate.

### The subtlest decision: max reach, global cap

How many months does a set of studies support?

**Reach has to be the MAXIMUM across studies.** Primary batches go on
stability as they are made: one batch at 24 months and two at 12 because
they started later is an ordinary ongoing programme. Taking the minimum
would report a normal filing as unsupported.

**A failure anywhere has to CAP it.** A shelf life is a claim about the
product, not about the luckiest batch. If one primary batch goes out of
specification at 12 months, "two of three held" is not a shelf life, it is
a deviation investigation.

The first version of this took the maximum only, and the AMPICLOX fixture
caught it immediately: with a planted failure at 12 months in batch one,
3.2.P.8.1 still cheerfully rendered "Shelf life: 24 months" because batches
two and three reached 24. That is precisely the defect the phase exists to
remove, so the combination — max reach, earliest failure caps it — is what
shipped. `supported_months` lives on the model layer for the same reason:
the renderer and the rule must not each compute their own.

### The summary cannot overstate the data

3.2.P.8.1's old template printed `{{ product.shelf_life_months }}` beside
`{{ study.result_summary }}` — a claimed period next to a typed sentence,
with nothing able to tell whether either matched the data. The page now
assembles its load-bearing sentence in the context builder, precisely so
that when the claim exceeds what the data supports it renders

```
[[SHELF LIFE NOT SUPPORTED: 24 months is claimed, but the long-term data
support 6 months (the last timepoint before the first out-of-specification
result, which is at 12 months). ...]]
```

instead of the claim. A template printing the two fields separately could
not make that choice, which is why the sentence is built in code.

### P21b: a grid, and what deviating cost

Every other collection in the wizard is a list of rows entered through one
generic form driven by `wizard-steps.ts`'s field specs. Stability is where
that stops working, and the reason is arithmetic: a real study is five
timepoints across eight tests — forty trips round an "add row" form, each
asking again which test and which timepoint this value is for. Those are
exactly the two questions a grid answers by POSITION.

**What the deviation costs, recorded rather than waved past:**

1. A second entry idiom to learn — everything else is add-a-row, this is
   fill-a-table.
2. `wizard-steps.ts` is no longer a complete answer to "what does the
   wizard ask for". It is an answer with a footnote, so the footnote lives
   in `ChildStepSpec.customEditor` where the next person adding a field
   will actually look, and a test asserts every step has either fields or
   a custom editor.
3. A second place validation is drawn — mitigated the same way the batch
   screen's is: same `src/lib/acceptance` module, advisory only, R23 is the
   gate.

**The paste is the feature.** Every stability dataset starts life in Excel.
`src/lib/paste-table.ts` is a separate module from the grid so the risky
half is testable without a browser, and three things the naive
`split("\n").map(l => l.split("\t"))` gets wrong all showed up in real
pastes: a quoted cell containing a newline tears one row into two; Windows
line endings leave a `\r` on the last cell of every row so "24" never
matches anything; and the trailing newline every spreadsheet adds produces
a phantom empty row. Anything unmatched is **reported, never guessed at** —
guessing which test a value answers is guessing which limit it will be
judged against.

### Two things only visible once it ran

- **`MissingGreenlet`, again, and from a new direction.** Six
  `test_module1_api` tests failed on `POST /projects` — nowhere near
  stability. `ProductRead` nests `stability`, and `StabilityStudyRead` now
  nests `results`, each of which derives `meets_criterion` through its
  specification test. That is three levels deep where the eager-load in
  `PRODUCT_CHILD_OPTIONS` was one. P20's build log recorded 53 tests
  failing this way; the lesson did not transfer because the *new*
  relationship was on a schema that already existed. Adding a nested field
  to a `*Read` schema is an eager-loading change, even when the model is
  untouched.
- **The router factory grew dotted load paths** rather than a second
  bespoke router, because `nested_collections=("results.specification_test",)`
  is the general form of the problem above. `db.refresh` still takes
  attribute names, so it gets the first segment of each path.

### Incidental fix

The finished product's control data had no home in the wizard. P20 built
3.2.P.5.1 and 3.2.P.5.4 and mounted the editor only under a drug substance
and an excipient, so a filer could not enter the drug product's own
specification at all — and without it the stability grid has no limits to
check against and no rows to offer. The stability step now mounts the same
`OwnerControlPanel` the API rows use.

### Contract bookkeeping

`stability_timepoints` is marked LANDED. Two leaves still cited it —
1.4.2 (QIS) and 2.3 (QOS) — and their blocker was **re-pointed, not
removed**, to a new `derived_document_assembly` capability. The data they
were waiting on now exists; the assembly is P24's job. Removing the blocker
would have flipped 2.3 to done, and its own note in the target warns
against exactly that: it is registered and rendering but is a thin
overview, and crediting it would launder the gap.

---

## P20 — One specification, three owners (2026-09-06)

**Platform capability: 32/98 → 43/98 leaves.** Eleven sections, and one
schema decision that the rest of Module 3's control sections now rest on.

### The decision the phase exists for

`SpecificationTest` was foreign-keyed to `active_ingredient`, so it was
drug-substance-only *by construction*. But 3.2.S.4.1, 3.2.P.4.1 and
3.2.P.5.1 are the same table — test, method, acceptance criterion, order —
asked of three different things. Building them separately would have meant
three tables, three editors, three rule sets, and the drift between them is
precisely what this platform exists to catch.

**Chosen: one nullable foreign key per owner type, plus a CHECK that
exactly one is set.**

```
active_ingredient_id  UUID NULL  REFERENCES active_ingredient(id)
product_id            UUID NULL  REFERENCES product(id)
excipient_id          UUID NULL  REFERENCES excipient(id)
CHECK ((CASE WHEN active_ingredient_id IS NULL THEN 0 ELSE 1 END) + ... = 1)
```

**Rejected: a discriminator column** — `owner_type VARCHAR` + `owner_id
UUID`. It is the tidier schema, it never changes when a fourth owner type
appears, and it is what the generic-foreign-key recipes reach for. It was
rejected because **`owner_id` cannot be a foreign key**, since a column
cannot reference three tables — so the database cannot enforce that the
owner exists. Delete an excipient and its specification rows survive,
pointing at nothing, with no cascade and no constraint violated. The first
symptom is a 3.2.P.4.1 that renders empty, or a batch analysis checked
against a specification belonging to nothing. Trading referential integrity
for schema convenience is the wrong trade in a system whose entire claim is
that its data cannot disagree with itself.

The cost is real and is schema churn: a fourth owner is a migration — one
column, one FK, one widened CHECK, one entry in `_OWNER_ATTRS`. That is the
honest price, because Module 3 has exactly three things with a
specification and the list is fixed by ICH M4Q rather than by this
codebase. The fourth owner is hypothetical; the orphan rows were a
certainty.

Two owner spaces, not one: `BatchAnalysis` and `Impurity` accept only the
drug substance and the drug product. The CTD has no excipient batch-analysis
or impurity leaf, and a row the dossier could never render should not be
storable.

**The migration widened; it did not move.** Every pre-P20 row keeps the
`active_ingredient_id` it had, which is what makes the CHECK satisfied by
every existing row before it is added — and what makes P13's tests pass
unchanged. `test_the_migration_widened_the_table_without_moving_a_row`
states that as a test rather than as a promise in a docstring.

### The rule that justifies the whole design

R22: a batch result outside its own specification's acceptance criterion is
an ERROR that names the batch, the test, the result and the limit.

The point is not the comparison, it is **where the limit comes from**.
`BatchAnalysisResult.specification_test_id` is a foreign key, so R22 reads
`result.specification_test.acceptance_criterion` — the same string 3.2.S.4.1
renders. There is no copy. Tighten a limit in the specification and every
batch already on file is re-judged against it with nothing re-entered
anywhere, which
`test_tightening_the_specification_re_judges_batches_already_on_file` pins.

It also makes the mistake unrepresentable rather than merely detectable: a
result for a test that is not in the specification has no row to point at.
The wizard's batch screen is a list of the spec's own tests for the same
reason, and the API refuses a cross-owner pairing with a 422 — not a 404,
because the test exists and the caller may legitimately know about it; what
is wrong is the pairing.

### Parsing an acceptance criterion, and the ordering bug that nearly landed

`acceptance_criterion` is text on purpose — real criteria are ranges, NMT/NLT
one-sided limits, "Complies", "Corresponds to reference spectrum" — so R22
has to read them. `app/validation/acceptance.py` is deliberately its own
module because it is the part of P20 most likely to be wrong.

Two things it gets right that a first draft would not:

**1. `None` is a third answer and never means "passed".** An unparseable
pair is reported as unchecked (one INFO per batch, not one per row, so the
report stays readable), because an unchecked result is not a passed result
and the difference has to be visible somewhere. Every branch returns `None`
rather than guessing.

**2. The non-conforming list is checked FIRST.** `"does not comply"`
contains `"comply"` — so a substring test in the natural order reads a
failure as a pass. That is the single most dangerous bug this module could
have, and it is the one a reasonable person writes. It is pinned by a test
case, in both languages.

A European decimal comma (`"0,15"`) is normalised rather than parsed as the
integer 15 — a hundredfold error, in the unsafe direction.

### The eCTD surprise: excipients repeat as an ELEMENT

P19 established that most repeating sections file several leaves under one
heading, because their DTD element is declared once with `leaf*` content.
Only 3.2.S had a repeating heading, and that looked like a drug-substance
peculiarity.

It is not. The DTD declares:

```
<!ELEMENT m3-2-p-drug-product (..., m3-2-p-4-control-of-excipients*, ...)>
<!ATTLIST m3-2-p-4-control-of-excipients  %att;  excipient CDATA #IMPLIED>
```

Starred, with an attribute naming the subject — structurally the same shape
as `m3-2-s-drug-substance`, arrived at from the other end of Module 3. So
`_place_drug_substance_leaf` became `_place_repeated_leaf` driven by a
`REPEATING_ELEMENTS` table, and `build_index_xml`'s `substance_info`
parameter became `repeat_info`. Adding a second parameter would have been
the second special case, which is the mistake P19's own build-log entry
warns about.

Without the discriminator this would have been the P13 `_Node` bug arriving
by a new route: both excipients' subtrees merged under one element,
producing a **DTD-valid** backbone that files one material's specification
under the other's name. A merge is far worse than a crash, because nothing
reports it.

One difference worth naming, because it is the spec making a judgement:
`substance` and `manufacturer` are #REQUIRED on the drug-substance element —
a drug substance cannot be filed anonymously — while `excipient` is
#IMPLIED. The DTD will accept an unnamed excipient section. This platform
always sets the attribute anyway: two specification leaves under one
heading, distinguishable only by filename, is a heading an assessor cannot
read.

### Sharing templates, and the binary that was deleted

Eleven sections, five templates. `specification.docx` serves 3.2.S.4.1,
3.2.P.4.1 and 3.2.P.5.1; `batch_analysis.docx` serves both batch sections;
`impurities.docx` both impurity sections; and the two hybrid shapes share
one each. The mechanism is the heading being `{{ section_number }}
{{ section_title }}` rather than a literal — the same mechanism P17's
fourteen not-applicable statements already share one template through.

P13's `section_3_2_s_4_1.docx` was **deleted**, not left beside its
replacement. An unreferenced binary template is exactly the thing that rots
unnoticed, and `git diff` would never show anyone that it had.

**The `{%tc %}` gotcha, which is P13's `{%tr %}` gotcha in the other
dimension.** The batch results table was first written as a matrix — one row
per test, one column per batch — using docxtpl's column loop with the tags
as paragraphs inside a cell. It dies with the same `Encountered unknown tag
'endfor'` the P13 entry recorded: the tags need *cells* of their own, just
as `{%tr %}` needs *rows* of their own.

The fix was not to fight the loop but to change the table, and the flat form
is the better document anyway: one row per test per batch, with the
acceptance criterion on the same line as the result. A limit printed in one
table and the numbers judged against it in another is the layout that lets
an out-of-specification result pass unnoticed. Flat also works for any
number of batches.

### Three things that only showed up when the code ran

**1. Every new relationship is a `MissingGreenlet` waiting to happen.** 53
tests failed at once because R22 walks batch → results → specification test
and R11 now reads impurity limits, none of which `app/api/loading.py`
eager-loads. The failure surfaces deep inside a synchronous rule, nowhere
near the query that forgot to load it. The `result → specification_test` hop
is the load-bearing one — it is how R22 reaches the limit without a copy —
and it happens to work through the identity map when the specification is
already loaded, which is exactly the kind of accidental correctness worth
spelling out explicitly instead.

**2. "Visual" is not a monograph citation.** The seeded drug-substance
specification's Description row cited its method as `"Visual"`, so
3.2.S.4.2's compendial/in-house classifier read it as in-house and asked for
a method description. The classifier was right; the fixture was wrong — a BP
monograph does carry a Characters/Description section, so the citation is
`"Visual, BP monograph"`. Worth recording because the failure direction was
chosen deliberately: a false negative (compendial read as in-house) asks for
a description that is already public — wasteful, harmless. A false positive
would tell an applicant they owe no method description when they do, which
is a deficiency letter.

**3. R11 had to learn to discriminate.** Extending the pharmacopoeial-version
reminder to impurity limits is only useful if it fires on a BP-derived limit
and *not* on an ICH Q3A/Q3B threshold — the latter does not move with a
pharmacopoeial edition, and a reminder to go check one is noise that teaches
the reader to ignore R11 entirely. Tokenising `limit_source` rather than
substring-matching it matters here: `"ep"` is inside `"except"` and inside
`"development"`.

### The browser has a second copy of the acceptance check, on purpose

The brief asked for out-of-specification results to show *at entry*, not at
export, and it is right about why: the person typing a certificate of
analysis has the paper in front of them and can check a transposed digit in
five seconds. So `frontend/src/lib/acceptance.ts` mirrors the Python.

Duplicating a rule is normally what this platform refuses. Two things make
it tolerable, and both had to be true:

1. **The copy is advisory and cannot gate anything.** The export gate is
   R22 on the backend. Wrong permissively, the build still blocks; wrong
   strictly, the filer sees a warning the report does not repeat. Neither
   can put a bad number in a package.
2. **It is pinned by a shared test table.** `acceptance.test.ts` carries the
   same cases as the backend's parametrised test, deliberately, so changing
   one without the other fails a test rather than drifting quietly.

If a third copy is ever wanted, that is the signal to make it an endpoint.

### Deviation from the prompt

The prompt asked for 3.2.S.4.5 (justification of specification, drug
substance) alongside 3.2.P.4.4 and 3.2.P.5.6. **`docs/target-toc.yaml` has
no 3.2.S.4.5 leaf** — the source dossier it was derived from does not file
one, and 3.2.S.4 stops at .4. Registering a section the contract does not
name would have put a document in the package that the coverage check
cannot see, so it was left out. The other two justification leaves are
built. If the real target does owe a 3.2.S.4.5, the fix is to add it to the
target first and let the check demand it — the contract leads, not the
registry.

### Known gaps

- `Certificate` still has no excipient link, so 3.2.P.4.5's TSE/BSE evidence
  is per product rather than per material (carried over from P19).
- 1.4.2 (QIS) and 2.3 (QOS) are no longer blocked by
  `spec_polymorphic_owner`, but remain blocked by `stability_timepoints`.
  The QOS is the highest-leverage document in the target and it needs both.
- `BatchAnalysis.batch_size` is free text, so nothing reconciles it against
  3.2.P.3.2's computed batch size. That check wants the same treatment R04
  gives the batch formula, and is a rule rather than a model change.

## P19 — The sections the data already supported (2026-09-06)

**Platform capability: 23/98 → 32/98 leaves.** Nine sections, all of them
backed by models and rules that already existed. The phase is cheap
coverage on purpose, and it buys something the expensive phases need: the
repeat machinery, exercised on three axes instead of one, before
`spec_polymorphic_owner` and `stability_timepoints` lean on it.

### The data model was ahead of the section registry

`BatchFormulaLine` had backed 3.2.P.1's composition table and rule R04's
salt-to-base arithmetic since the vertical slice, and 3.2.P.3.2 *is* that
table scaled to a batch — it simply did not exist. `Packaging` had backed
R12 since P06 and 3.2.P.7 did not exist. `Manufacturer` was fully modelled,
with roles, and neither 3.2.S.2.1 nor 3.2.P.3.1 existed.

What blocked them was not data. It was that `instances.py` repeated along
exactly one axis, hard-coded in a module constant.

### What generalising the axis actually broke

The prompt asked for the assumptions the drug-substance implementation had
encoded. There were six, and none of them was visible before writing the
second axis — which is the general lesson: a single-case implementation
does not look like it is making assumptions, because with one case every
assumption is true.

**1. "Has a subject" meant "repeats per drug substance".** `drug_substance_
info()` — which the eCTD backbone calls to fill the DTD's required
`substance` and `manufacturer` attributes — iterated every instance with a
subject and asked it for `.inn_name`. The moment a pack became a subject,
that function was one build away from asking a blister for its INN. It now
tests the axis explicitly. This is the general shape of the bug: a
predicate that was an identity when there was one axis becomes a wrong
guess when there are two.

**2. Subjects were assumed to have distinct names.** Two actives of one
product cannot share an INN, so `3.2.S.1-ampicillin` could not collide with
its sibling and nothing ever checked. Two PRIMARY packs with no material
recorded both slugify to `pack-primary` — one folder, one filename, and the
second document silently overwriting the first on the way into the package.
`_reject_colliding_subjects` now raises, in the same spirit as
`folder_for_section`: a leaf lost at build time is a leaf nobody notices is
missing until an assessor does. **How it announced itself:** it did not.
The three-pack test passed with four packs and would have passed with three
had two of them collided; the collision was found by reading the label
function, not by a red test. The test came second.

**3. The folder map assumed the `32s/` shape.** `DRUG_SUBSTANCE_FOLDERS`
held path tails and `folder_for_section_instance` hard-coded the prefix
around them. `RepeatFolders` (base + prefix + tails) makes the per-subject
segment one string per axis — which matters because that segment is inside
MD5-checksummed paths, so a second copy of it is a second thing that can
drift.

**4. `index.xml` looked up heading paths by the whole instance key.** That
worked while the only repeating sections were the ones routed through
`substance_info`. A `3.2.P.7-pack-hdpe` key would have found no heading
path and been *silently skipped* — written to disk, checksummed, listed in
the CTD table of contents, and invisible to the agency's software. Exactly
the P18 failure mode, arriving by a new route. The lookup now strips the
subject suffix (a section number never contains a hyphen).

**5. Nothing guaranteed the ORDER subjects came back in.** No relationship
on `Product` declares an `order_by`, so the order is whatever the database
returns — and in PostgreSQL an UPDATE physically moves a row, so a project
edited between two builds can hand its packs back in a different order. The
paths would survive that (they carry the subject's name, not an index), but
the package's file order would not, and **a zip whose entries move is not
byte-identical** — which is AGENTS.md §5's rule and the thing the eCTD
lifecycle's diff model rests on. `expand_sections` now sorts subjects by the
same slug that names their folder, so the two orders are one order.

**6. A Python-side column default is applied at FLUSH, not at
construction.** `Packaging.role` defaults to DRUG_PRODUCT, so an in-memory
object — a seed, a test fixture, an API create before the flush — has `role
is None`. Filtering 3.2.P.7's packs with `role is DRUG_PRODUCT` therefore
dropped every pack from a dossier built before a commit: a container closure
system silently absent from the package. The filter is now negative
(`is not DRUG_SUBSTANCE`), which also matches what the migration's
`server_default` says about rows written before the column existed. 3.2.S.6
keeps the positive test on purpose — "this drum holds the API" is a claim
about a material, and a claim must be made, not defaulted into.

### Only 3.2.S repeats as an ELEMENT; the rest repeat as leaves

Worth writing down because it looks like an inconsistency and is not.
`m3-2-s-drug-substance*` is starred in the ICH DTD with two #REQUIRED
attributes, so two actives are two heading elements. But
`m3-2-p-7-container-closure-system` and `m3-2-p-3-1-manufacturers` are each
declared once, with `leaf*` content — so three packs are three leaves under
one heading. The CTD folder tree still gives each its own folder (a pack per
folder is how a human navigates it); the backbone does not, because the DTD
says otherwise. Placement and folders answer to different authorities.

### One Packaging model, two sections: role, plus a link

The prompt was explicit: do not let one `Packaging` serve 3.2.S.6 and
3.2.P.7. `PackagingRole` (DRUG_PRODUCT / DRUG_SUBSTANCE) is the answer to
that, and it cannot be inferred from `component` — a fibre drum is as
PRIMARY to an API as a blister is to a tablet.

The role alone was not enough, and this only became visible once 3.2.S.6 was
built as a *per-substance* section: with a product-scoped Packaging table,
every API's 3.2.S.6 would list every API's drums. So `Packaging` also gained
a nullable `active_ingredient_id`. Null means "applies to every substance",
which is the ordinary case (one API, or two shipped alike) and preserves
every existing row's meaning.

### A rule that predated the role had to be told which material it meant

R12 (declared pack size appears on some artwork/label/carton) was written
when `Packaging` could only mean the finished product. The moment it could
mean two things, the rule was reading rows it had never been asked about --
an API drum's label is not where the medicine's pack size is printed, and
a drum whose description happens to contain the pack size would have
satisfied a check about a carton the product may not even have. It now
excludes drug-substance rows. Worth noting as a category: **adding a
dimension to a model quietly changes every query that predates it**, and
those queries do not fail, they just answer a subtly different question.

### 3.2.R lives in the region profile, and the leaf still lives in the registry

3.2.R is the one part of Module 3 that is regional by definition, so a
common table could only ever hold one region's answer. The split: the
SECTION is registered like any other (assembly, folders, the backbone and
the section list pick it up with no special case), and its CONTENT comes
from `RegionProfile.regional_information`. An empty list produces a leaf
that says the region declares no additional regional information — the same
call P17 made about empty folders. **The NAFDAC list is unconfirmed against
the current guideline and says so in a comment**, matching the target TOC's
own `confirmed_against_guideline: null`.

### 3.2.P.4.5 and R21: a statement generated from a field that had to exist

An excipient's origin cannot be derived from its name. Lactose is bovine
milk, gelatin is bovine or porcine, and magnesium stearate is vegetable in
one plant and tallow-derived in the next. Hence `ExcipientOrigin` on the row
and rule **R21**: an excipient declared of human or animal origin with no
TSE/BSE certificate on file is an ERROR that blocks export.

Three deliberate calls in that one rule:

- **A null origin says nothing.** "Not stated" is not "synthetic". Erroring
  on unclassified excipients would block every project that predates the
  field, on data nobody has been asked for. The rendered leaf names those
  materials instead and says the statement does not cover them — a claim the
  filer never made must not appear in their dossier.
- **ERROR, not WARNING** — R20's reasoning, not R19's. The platform is not
  guessing: the filer positively declared animal origin, and the certificate
  is either on file or it is not.
- **KNOWN LIMITATION: one certificate satisfies every animal-origin
  excipient.** `Certificate` has no excipient foreign key. A dossier with
  gelatin capsules and bovine lactose from two suppliers owes two
  certificates and this rule sees one. There is a test pinning that
  behaviour so it reads as a decision rather than a surprise; fixing it is a
  migration, not a rule change.

`CertificateType.TSE_BSE` also has **no `DocumentSlot`**, which means R20
(no applicable leaf ships a placeholder) cannot cover it. That is not an
oversight: NAFDAC's Module 1, as recorded in the target TOC, has no declared
leaf number for a TSE/BSE certificate, and inventing one would put a
fabricated leaf number in a package. R21 gates the certificate's existence;
placement waits for a confirmed leaf.

### Reference standards without a reference-standard model

3.2.S.5 and 3.2.P.6 have no data source in the target TOC and no model here.
Rather than defer them or invent catalogue numbers, both are DERIVED from
`compendial_std`, which is a fact already on file: claiming BP means using
the BP reference substance for that monograph; claiming in-house means a
characterised working standard, cross-referenced to where its
characterisation is filed. Deterministic, truthful, and it names no
catalogue number nobody entered.

### The batch formula cannot disagree with the composition table

Both read `product.batch_formula`. Neither holds a copy. `test_batch_formula
_cannot_disagree_with_the_composition_table` fails the moment someone
"fixes" one of them by typing the numbers in. The batch column is computed
(qty/unit × batch size), never read from `declared_batch_qty_kg` — that
field is the filer's claim, and R04 exists to check it against exactly this
arithmetic. Printing the claim would file the unchecked number.

### Scope calls

- **The `excipient` axis is registered and unused.** 3.2.P.4.1 still waits
  on `spec_polymorphic_owner`. The axis is here because the target TOC names
  it and a test holds the two together — adding that section is now a
  registry entry rather than another branch in `instances.py`.
- **3.2.P.4.1's `blocked_by` lost `repeat_axis_generalisation` but keeps
  `spec_polymorphic_owner`**, so it correctly still reads `blocked`.
- **Uploaded per-substance leaves still do not reach `index.xml`.**
  `drug_substance_info` only covers registered sections, so an uploaded
  3.2.S.3.1 gets a folder but no backbone entry. Pre-existing (P18), not
  introduced here, and worth its own fix.

### What you learned

**Software**
- A hard-coded branch and a lookup table are the same code until the second
  case arrives; the table is what makes the second case an edit to data.
- When one axis becomes many, the bugs are in the predicates that used to be
  identities ("has a subject" ⇒ "is a drug substance") — those fail silently
  because they were never wrong before.
- Uniqueness that came free from the domain (INN names) has to be enforced
  explicitly the moment the domain changes (packs).

**Regulatory**
- 3.2.S.6 and 3.2.P.7 are the same question about different materials, and a
  container closure system filed against a material it was not qualified for
  is a real defect, not a formatting one.
- 3.2.P.3.1 is about the drug product: the API site belongs in 3.2.S.2.1, and
  putting it in both names the wrong company as the maker of the medicine.
- A TSE/BSE statement is a claim about materials, so it can only be as good
  as the origin data behind it — which is why an unclassified excipient has
  to be named rather than swept into the statement.

**Next:** P20 (specifications and batch analyses), which needs
`spec_polymorphic_owner` — the capability that unblocks five leaves,
including the excipient axis registered but unused here.

---

## P18 — The upload path (2026-09-04)

**Platform capability: 23/98 done, and the 22 `upload_path` leaves move from
`missing` to `placeholder` — every one of them now has a route by which a
real file can arrive.** The headline number deliberately does NOT move for
those 22, which is the most important thing in this entry; see "two kinds of
coverage" below.

### What actually changed

Before this phase the platform could build a structurally perfect eCTD
package in which roughly a quarter of the leaves were pages reading
"PLACEHOLDER — REPLACE THIS FILE". `Certificate` was metadata only and said
so in its own docstring; MinIO had been wired since P04 but only BUILDERS
ever wrote to it, and `artifacts.py` was download-only. There was no route by
which a regulatory affairs officer could attach the actual CPP.

`SectionDocument` is that route. It is keyed by section INSTANCE (number +
subject slug) rather than section number, for the reason `instances.py`
already argued for rendered documents and which is stronger for uploaded
ones: "3.2.S.3.1" does not name one document once a product has two actives,
and an elucidation-of-structure report is about ampicillin OR cloxacillin.
Filing one under a number meaning "both" puts the wrong molecule's spectra in
front of an assessor.

### The non-PDF decision: convert at upload

Three options, and the checksum settles it.

The eCTD manifest and `index.xml` publish an MD5 over the bytes that ship. If
a `.docx` were stored as-is and converted during the build, the checksum
could only be computed at build time, and the file a user sees listed on the
section screen would not be the file being checksummed. **Converting at
upload means the bytes, the size and the MD5 are settled at the moment of
upload and never change afterwards** — the shipped file and the recorded
checksum are the same object by construction, not by care.

It also fails at the right time. A conversion that goes wrong is the
uploader's problem and they are standing right there. Discovering it during a
build, weeks later, possibly by someone else, turns a five-second fix into an
incident.

**Rejecting non-PDFs outright was the third option and it loses on contact
with reality**: a letter of access genuinely arrives as a Word document, and
telling a regulatory affairs officer to convert it by hand is asking them to
do, less reliably, something this codebase has done deterministically since
P07.

**Images are refused on purpose.** A scanned JPEG is a real thing people
have, but wrapping it in a PDF container produces a leaf with no extractable
text — which agency validators flag and reviewers cannot search. Refusing
with an instruction ("scan or export to PDF") is more honest than accepting
something that will be rejected further downstream, where the feedback is
worse.

And the declared `content_type` is treated as a hint, not as truth: it is
whatever the client says it is. The magic number is a property of the file.

### Versioning: replaced in place, deliberately

**Uploading twice replaces; there is no history.** This is a simplification
and it is the one a regulatory audit will eventually want undone — "what did
we file in sequence 0000, and who changed it before 0001" is a question this
table cannot answer today.

What makes it acceptable for now: **eCTD lifecycle already versions at the
SEQUENCE level** (P09). Once a sequence is submitted its leaves are frozen by
their checksums, so the history that matters to a REGULATOR is preserved even
though the working copy's history is not. What is lost is internal
provenance, and the day someone asks for it, the fix is a
`section_document_version` child table plus a pointer to the current row —
not a redesign.

A related deliberate choice: **detaching a document does not delete the
stored object.** A detach is usually "I attached the wrong file"; the cost of
orphaned bytes is a little storage, and the cost of deleting the right file
by accident is a CPP that takes weeks to reissue.

### An uploaded leaf ships byte-for-byte, bookmarks and all

P07 gives every RENDERED leaf a bookmark from its known section title, and a
test asserts it. Uploaded leaves are deliberately exempt, and the reason is
the checksum again: the MD5 is computed at upload and is already published in
the manifest and the eCTD backbone, so adding an outline entry afterwards
would silently make every published checksum wrong.

The alternative -- bookmark at ingest, before checksumming -- is technically
available and was rejected for a different reason: it means modifying a third
party's signed document. Real eCTD publishers do add bookmarks to supplied
PDFs, so this is a defensible thing to revisit, but doing it silently to a
regulator's signed CPP is not something to slip in without deciding it on
purpose.

**The trade-off, stated plainly: uploaded leaves carry whatever bookmarks
their author gave them, which may be none.** What is guaranteed is that they
are searchable PDFs rather than images, which is enforced at upload.

### Two kinds of coverage, and why the number did not jump

This is the subtlest thing in the phase and it nearly went wrong.

The naive move was to let the 22 `upload_path` leaves count as `done` now
that they can be attached. That would have been the exact laundering P16
exists to prevent: **a route to attach a CPP is a property of the PLATFORM;
the CPP actually being in is a property of one FILING.** Reporting the first
as though it were the second produces a green number for a dossier with no
paper in it.

So `resolve_status` gained an `attached` set, the script gained
`--project <id>`, and the report now labels itself: "platform capability" or
"project <id>". Without a project, an attachable-but-empty leaf reads
`placeholder` — the honest state, and the same word the check already used
for a certificate slot with no certificate.

### R20 and the blast radius of a gate that means it

`R20` is an ERROR: an applicable leaf standing on a placeholder blocks the
build. That is the severity model working as designed — a placeholder's whole
purpose is to make a gap loud, and shipping one is submitting a note
admitting the submission is incomplete.

**The interesting part was what it broke.** Every seed fixture models a
COMPLETE filing, which is what makes them useful for testing assembly and the
builders. The moment R20 existed, every one of them became a blocked filing,
and a dozen tests failed. Two ways to fix that:

1. Teach those tests to override R20.
2. Give the fixtures the documents a finished filing has.

**The first would have been the same fixture with the new gate switched
off** — the tests would go green and prove less than they did before. So
`app/seed/documents.py` attaches stand-in documents through the real
`ingest_document` path, which also means the seeds exercise validation,
conversion and checksumming rather than bypassing them.

**One place R20 deliberately stays silent**: a certificate type the region
has no declared leaf for. EU has no Module 1 document slots, so there is
nowhere to attach — and a gate you cannot pass is not a gate, it is a wall.
It would block every EU export with an instruction the platform gives no way
to follow. The gap is real and it is EU Module 1 being unmodelled, which
`EU_PROFILE` already says of itself; declaring those slots turns the rule on
for EU with no change to the rule.

### Three async/ORM traps, all the same shape

All three were "a plain attribute access did IO", and under the async engine
that does not merely block, it raises `MissingGreenlet`.

- **`project.documents` on a committed, Python-built project.** R20 reads it;
  the collection had never been loaded, so reading it went to the database
  from inside a synchronous rule. Fixed by initialising the collection in
  `Project.__init__`, the same move P17 made for `condition_answers`. Objects
  loaded from a query are unaffected — SQLAlchemy does not call `__init__`
  when it materialises a row.
- **Appending to that collection in the seed helper.** Same cause, different
  caller; `set_committed_value` says "this collection is already loaded, here
  it is" without the SELECT.
- **`id` was `None` until flush.** `default=uuid.uuid4` fires at INSERT, which
  was harmless while ids were only database keys. It stopped being harmless
  the moment ids became part of OBJECT STORAGE PATHS: computing
  `projects/{id}/documents/...` from `None` produces a key that looks
  plausible, stores real bytes, and belongs to no project. `Base.__init__`
  now assigns it at construction.

  That last fix had its own trap worth recording: **SQLAlchemy installs its
  `_declarative_constructor` only on classes that do not define `__init__`.**
  Defining one on `Base` means `super().__init__(**kwargs)` reaches
  `object.__init__`, which rejects keywords outright — every model
  constructor in the codebase broke at once, with a message
  ("object.__init__() takes exactly one argument") that says nothing about
  the real cause.

### Certificate types found by checking, not by thinking

Three were missing: certificate of incorporation (1.2.3), superintendent
pharmacist's annual licence to practice (1.2.11), certificate of registration
and retention of premises (1.2.12). All three are about the APPLICANT as a
business rather than about the medicine — which is exactly why a list written
while thinking about product quality missed them, and exactly the kind of gap
the target TOC exists to surface.

---

## P17 — Applicability as data, and the statements it owes (2026-09-04)

**Coverage: 9/98 → 23/98 leaves.** The largest single jump so far, and the
cheapest — fourteen leaves whose entire content is one generated page.

### The defect, which did not look like a defect

The source dossier declares its own scope three times, in print: Modules
2.4–2.7 not applicable, Module 4 not applicable, only 5.3.1 applicable. This
platform expressed all three by having nothing there. To an assessor an empty
`m4` folder and a declared exclusion look nothing alike — the first reads as a
packaging failure, the second as a scoped filing. `ectd/scaffold.py` even said
so in its own docstring ("nothing to scaffold for the empty m4/m5 module
folders"), which is now the clearest example in the repo of a comment that
documents a gap while sounding like a design decision.

The deeper problem was that applicability was **implicit in which sections
happened to be registered**. That works for exactly one submission type, and
there was no switch to flip the day a new chemical entity or an FDA filing
arrives.

### Why applicability is on Project, not Product

This is the distinction a future contributor will get wrong, so it is worth
stating plainly.

`SubmissionType` sits on `Project` because **the same medicine can be filed
generically in one market and as a full application in another**. Amlodipine
is a generic to NAFDAC; the identical product could be the subject of a
different kind of application elsewhere. Scope is a property of the FILING,
not of the molecule — the same reasoning that put `Applicant` on Project in
P15a (who is legally submitting is per-filing; a local agent in Lagos and a
different agent in Accra, one product).

**The rejected alternative was `Product.submission_type`**, which is tempting
because "is this a generic?" *feels* like a fact about the medicine. It is
not. Putting it there would mean a product could not be filed two ways
without being duplicated in the master data — and duplicated master data is
precisely what every other design decision in this codebase is arranged to
prevent. The tell that it is a filing property: it is the region profile,
keyed by *region*, that knows what the submission type implies.

### The applicability table is read, not retyped

`docs/target-toc.yaml` already carried `applicable`, `condition` and
`not_applicable_reason` for all 98 leaves. Hand-copying those into
`region_profiles.py` would have created two truths about what a dossier owes,
with no way to tell which one a package was built from. So `app/target_toc.py`
loads the contract into the application and the region profile builds its
table from it. The target file was promoted from "a document CI checks
against" to config — which it always was: a declarative, versioned,
re-confirmable table of regulatory facts.

The second submission type (`NEW_CHEMICAL_ENTITY`) is **derived** from the
first by promoting exactly the leaves the multisource guideline excuses back
to REQUIRED. That states the one regulatory fact distinguishing the two, and
cannot drift when a leaf is added. It is deliberately not a real model of an
NCE filing — nobody has confirmed the rest against NAFDAC's guidance — and it
is honest about that, the same call `EU_PROFILE`'s empty requirement lists
already make. It exists to prove the seam works.

### The bug the derivation had, and how it announced itself

The promotion matched the citation with `== MULTISOURCE_GUIDELINE`. The check
printed a clean-looking NCE table that still filed six not-applicable
statements across Module 5. The cause: the YAML spells the citation two ways —
`"...multisource (generic) pharmaceutical products"` for Modules 2 and 4, and
`"...multisource — only 5.3.1 applicable"` for Module 5, because the Module 5
statement genuinely says something more specific. Equality silently excused
six leaves in a filing that owes them. Now matched as a prefix, with a comment
saying why. **The symptom to recognise: a derived config table that is right
for most of its rows and quietly wrong for one module.**

### Three states, not two

`Applicability` is REQUIRED / CONDITIONAL / NOT_APPLICABLE, and the third
state is the interesting one. CONDITIONAL is a *question* — only the filer
knows whether their drug substance has a CEP or whether they are claiming a
biowaiver. Modelling it as a third state is what lets rule **R19** notice that
nobody has answered.

That distinction runs all the way to the UI, where the control is three
buttons rather than a checkbox: a default-unchecked box would silently answer
"no" on the filer's behalf, and "no" is not silence — it is a positive claim
that files a statement into the dossier. Unanswered, "no" and "yes" are three
different things and the API keeps them three (`null` retracts; `false`
asserts).

### The two rules, and why one gates and the other does not

- **R18 (ERROR)** — a section declared not applicable that nonetheless has
  content. Not an omission: a self-contradiction the package would state out
  loud, containing both "Module 4 is not applicable" and Module 4 material.
  An assessor cannot tell which the applicant means, and the charitable
  reading — that the statement is unchecked boilerplate — damages every other
  declaration in the filing. The applicant has to decide which is true.

- **R19 (WARNING)** — an unanswered condition. Never a gate: the platform
  cannot compute whether a biowaiver is being claimed, and refusing to export
  until every question is answered would make an unrelated filing unshippable
  over a question that does not apply to it. But silence must not be
  invisible either — an unanswered 1.2.17 is exactly how a biowaiver claim
  goes quietly missing from a dossier that otherwise validates clean, and the
  applicant then learns it from the agency rather than from us.

### One emit path, resisted twice

The statements go through the ordinary section pipeline: one
`na_statement.docx`, registered as fourteen `SectionSpec`s with
`is_statement=True`, so assembly, folder placement, the TOC and the eCTD
backbone pick them up with no special case. Per-project filtering happens in
`expand_sections`, which is the one place that already knew "what documents
does THIS project owe".

A separate emit path was the obvious shortcut and would have been a second
pipeline to keep in sync — the same reasoning that keeps repeated 3.2.S
sections in the registry rather than in a bespoke builder. The payoff showed
up immediately and for free: `scripts/check_target_toc.py` credited all
fourteen leaves with a two-line change, because they were already in
`SECTIONS`.

### Storing the answers: JSON, and what would change our mind

`Project.condition_answers` is a JSON column keyed by section number. The
rejected alternative was a `ProjectCondition` child table, which is the more
typed instinct and would have been the right call if the keys were a fixed
enum. They are not — they are section numbers owned by config, so the table
would buy an FK the database cannot enforce plus a migration every time a
condition is added to the profile.

**What would change our mind:** the day an answer needs an author and a
timestamp. At that point it stops being a scoping switch and becomes an
auditable regulatory assertion, and it earns its own table.

### A trap worth remembering: SQLAlchemy defaults fire at flush

`mapped_column(default=...)` runs when the row is INSERTed, not when the
object is constructed. The first test failed with an empty statement list
because a freshly built `Project` had `submission_type = None`, so the
applicability lookup returned an empty table — every section silently
unmodelled. That is the "we don't know what this dossier owes" state P17
exists to remove, and it should not be reachable even for the milliseconds
before a commit. Fixed with a `__init__` that `setdefault`s both P17 fields.
**Symptom to recognise: a feature that works through the API and produces
nothing in a unit test that builds the object directly.**

### Four things the full suite caught that unit tests did not

Each is a different way a change of this shape breaks something at a
distance, and all four are worth recognising again.

1. **`resolve_applicability` crashed for an unmodelled region.** R18/R19 run
   on every project; `get_region_profile` raises for FDA by design (a builder
   asked to package an unconfigured region must fail loudly, not guess). But
   a *rule* must not crash readiness for a region nobody has modelled. It now
   treats "no profile" and "an empty table" as the same statement — nothing
   declared, so nothing claimed — which is what EU_PROFILE already says.
   The symptom was a P06 test about a completely unrelated rule (R13) failing.

2. **The table of contents grew onto a second page.** The test asserting
   every document is listed read only `pages[0]`, so widening it to every
   page was the obvious fix — and it still failed, on a different row. The
   real cause was in the DOCUMENT, not the test: Word splits a long table
   row across a page break by default, and a split row also interleaves its
   two columns in extracted PDF text, so half a title lands in the middle of
   a path. `w:cantSplit` on every data row and `w:tblHeader` on the header
   fix both problems at once — a reviewer now gets column headings on every
   page and never a document whose title and path are on different pages.
   Worth noting how thin the first fix was: it made the symptom move rather
   than go away, which is usually the sign that the defect is somewhere
   other than where you are looking.

3. **The seed dossiers were permanently mid-question.** R19 warned about ten
   unanswered conditions on fixtures that model *finished* filings, which
   broke the "a clean dossier has no ERROR or WARNING findings" assertions.
   The fix was to answer them in the seeds — a conventional generic claims
   none of them — rather than to teach those assertions to ignore R19.
   Silencing the rule to keep a test green would have thrown away exactly the
   signal the rule exists to give.

4. **The PDF cache made an error-path test unreachable.** The test asserting
   a missing `soffice` binary raises cleanly converts a document an earlier
   test already converted, so the cached answer came back and the failure
   path never ran. The cache is *correct* there — the bytes are already
   known — so the fix is `clear_conversion_cache()` in that one test, not a
   weaker cache. Worth noting as the honest qualification to "a cache here
   cannot change behaviour": it cannot change a **result**, but it can hide a
   broken environment.

### The DTD had one more opinion: 5.3.5 repeats per indication

Thirteen of the fourteen statements file under the heading their section
would occupy. `m5-3-5-reports-of-efficacy-and-safety-studies` refused: the
DTD declares it starred and repeating **per indication**, with `indication`
#REQUIRED — the same shape `m3-2-s-drug-substance` has for substances.

A not-applicable statement has no indication to name, and supplying one
("not applicable", or the product's own indication) would write a fabricated
regulatory fact into the backbone. So that statement is filed one level up,
as a leaf directly under `m5-3`, whose content model begins with `leaf*` and
permits exactly this. It reads better anyway: the statement speaks for the
whole of 5.3.5 rather than for one indication inside it — the same reasoning
that gives Module 4 a single "4.0" page. Only the backbone placement moves;
the CTD folder is unchanged, because only the backbone carries the
constraint.

**How it announced itself:** `build_index_xml` raising
`DTD_MISSING_ATTRIBUTE: Element m5-3-5-... does not carry attribute
indication` — which is the system working. The EU-region eCTD build tests
could never have caught it, since applicability is only modelled for NAFDAC,
so the fourteen hand-typed heading paths get a DTD test of their own.

### A scope call: which conditional "no" actually files a statement

The P17 plan says answering "no" to a conditional section produces its
not-applicable statement, and lists seven — five of them in Module 1 (1.2.13
previous MA, 1.2.15 CEP, 1.2.16 APIMF letter of access, 1.2.17 and 1.2.18
biowaivers). What is actually built emits a statement only for the leaves the
target TOC declares `production: na_statement` — which covers 3.2.P.4.6,
3.2.A and 5.3.1.3, but not the Module 1 five.

**Why:** the target TOC declares 1.2.15 as `uploaded`, not `na_statement`.
Emitting a statement there would mean this code silently disagreeing with the
contract about how that leaf comes into existence — the exact two-truths
problem the rest of this phase was arranged to avoid. And Module 1 folder
placement comes from the region profile's `module1_slots`, not
`MODULE_2_5_FOLDERS`, so those statements have nowhere to go; the same plan's
folder-placement task lists only the `na_statement` leaves, which is
consistent with the reading taken here.

The answers themselves ARE captured, stored, validated by R19 and shown on
the section list — only the leaf is not emitted. **To finish it properly:**
change those five entries in `docs/target-toc.yaml` to `na_statement`, give
Module 1 statements a slot in the region profile, and they will flow through
the existing pipeline with no new code. Deliberately left as a visible gap
rather than resolved by quietly contradicting the contract.

### The cost, and the fix it forced

Every CTD/eCTD build now converts fourteen more DOCX leaves through
LibreOffice — about a second each, on every build, in a test suite that
rebuilds constantly. The suite went from tolerable to roughly an hour, which
is the point at which nobody runs it locally and CI becomes a lottery.

The fix was already sitting there in P07's own contract: `convert_docx_to_pdf`
guarantees that identical input bytes produce identical output bytes (that is
why the `/CreationDate` and `/ID` are pinned — P09's checksums depend on it,
and a test asserts a rebuilt package is byte-identical). A function with that
contract is trivially cacheable: a bounded `lru_cache` on (docx bytes,
bookmark title) cannot change a single result, it can only skip work whose
answer is already known.

The general lesson is worth keeping: **the determinism the regulator forced
on us turned out to be the property that made the optimisation safe.** The
checksum requirement is usually experienced as a constraint; here it paid
back directly.

---

## P16 — The target TOC as the contract (2026-09-04)

**Starting coverage: 9/98 leaves.** Every phase from here is measured as a
delta against that number.

`docs/target-toc.yaml` was derived leaf-by-leaf from a filed NAFDAC
multisource dossier (Me Cure, Amlodipine Tablets 5 mg): 98 leaves, each
declaring whether it is applicable, how it is produced, what it repeats over,
and which capability blocks it. `scripts/check_target_toc.py` compares that
target against what the platform can actually render. This phase fixed two
defects that made the number untrustworthy, and put the check in CI.

### Two ways a check can lie

Both defects produced a report that looked fine.

- **The import path defect.** Run as `python scripts/check_target_toc.py`,
  Python puts `scripts/` on `sys.path` instead of `backend/`, `app` fails to
  import, and the script's own `except` turned that into `unknown` for all 98
  leaves — a report that had checked nothing, exiting 0. Run as
  `python -m scripts.check_target_toc` from `backend/`, the same script
  answered 6/98. Fixed by pinning `backend/` onto `sys.path` at import time,
  so the invocation cannot change the answer, and by **raising** instead of
  returning `unknown` when the app will not import. Universal ignorance
  reported as a clean exit is worse than no check at all.

- **The single-source defect.** `registered_keys()` read only
  `templating.registry.SECTIONS`, but that is one of three producers. Module 1
  documents come from `region_profiles.NAFDAC_PROFILE.module1_slots` plus the
  `templating/certificates.py` and `templating/declarations.py` renderers. So
  1.2.4–1.2.6 (Power of Attorney, notarized declaration, contract
  manufacturing POA) reported `missing` while they genuinely render, and the
  certificate slots reported `missing` when they have folder placement and a
  placeholder path. Renamed to `producible_keys()` and unioned both sources:
  **6/98 → 9/98**, with five certificate leaves moving `missing → placeholder`.

### Where the leaf-to-producer mapping lives, and why

A certificate or declaration slot has no single section number — it holds
several leaves. The obvious fix is to list those leaf numbers in the script;
the reason not to is that the contract would then have two copies, and the one
in the script would drift. Instead the script asks the *profile* what a slot
accepts (`certificate_types` / `declaration_types`) and asks the *target* which
leaves that backs (`data_sources: [Certificate]` / `[Declaration]`). Each file
answers the question it actually owns.

### `placeholder` is its own status, deliberately

A leaf with `production: uploaded` and a slot but no file is `placeholder`, not
`done`. That distinction is the entire point of the check: the platform's
largest gap is that there is no route by which anyone attaches the real CPP PDF
(22 leaves blocked on `upload_path`), and crediting a placeholder as a finished
document would launder that gap into a green tick.

### CI without `--strict`, on purpose

The check runs on every push alongside ruff and black, but **not** with
`--strict`. `--strict` exits 1 on any gap, which today fails every build, and a
permanently red build teaches everyone to ignore the build. The comment in
`ci.yml` says when to switch it on: as coverage approaches complete, at which
point the report stops being information and becomes a gate.

### Tests

`tests/test_target_toc.py` — the one that matters is
`test_every_blocker_names_a_declared_capability`: a typo'd `blocked_by` still
parses, still counts, and reports under a heading nobody recognises, and when
the capability it meant to name is finally built, that leaf never unblocks.
Nothing about reading the YAML would show it. Also pinned: the 1.2.4–1.2.6
credit, the certificate `placeholder` status, and that no `status:` value in
the YAML has been hand-edited (`status` is computed; a hand-maintained status
column is a status column that lies).

**Next:** P17 (applicability and N/A statements) — 14 leaves blocked on
`na_statement_generator`, 11 on `applicability_profile`.

---

## P15 — Module 1, and the override made honest (2026-09-04)

The P14 audit ended on a finding that had nothing to do with ownership: a
NAFDAC dossier could not be finished in the browser at all. R13, R14 and
R16 blocked every export, and the three entities that would clear them —
Applicant, Certificate, Declaration — had models and document renderers
since P08 but no schemas, no routers, no UI. The only way to a package
was a validation override, which is meant to be a deliberate exception
rather than the normal route to an export.

### Three entities, three scopes, and why they differ

Worth restating, because they look interchangeable and are not:

- **Applicant → Project.** Who is filing is a property of the *filing*.
  The same product is filed by the manufacturer at home and by a local
  agent in Nigeria; one Product, two Projects, two applicants. Many-to-one,
  because an agent handling twelve products is one legal entity.
- **Certificate → Product.** A CPP attests to the *medicine*. It stays
  true across filings, so re-filing should not re-enter it.
- **Declaration → Project.** A Power of Attorney names a representative
  for *this* submission; next year's renewal may appoint someone else.
  Hence the cascade delete — a per-filing document outliving its filing
  would be a compliance error, not a convenience.

### The ownership hop the plan got wrong

The plan claimed declarations would need `owner_via` to walk two
relationships and that the factory needed teaching. It did not: the
parent is Project, and Project → Product is *one* hop, exactly what the
specification router already does. The correction cost nothing because it
was made before the code — but it is a fair warning about planning
against a mental model of a factory instead of reading it.

Applicant is the case that genuinely could not reuse the pattern. It is
reached directly through `/applicants` rather than through a Product, so
it has no owner to borrow and becomes the second owned root. Its
migration could backfill from the real relationship (applicant ← project
→ product.owner_id) rather than guessing at the earliest user, which is
what P14a had to settle for.

`Project.product_id` and `applicant_id` are both re-pointable FKs, and
only creation had been checking them. Moving a project onto someone
else's product would have silently handed it away; naming someone else's
applicant would have leaked their contact details through your own
project's reads. Both are re-checked on PATCH now, both have probes.

### Requirements were stated twice

R13 and R16 held NAFDAC's required certificate and declaration types as
constants in the rule engine. The wizard needed the same list to know
which Module 1 fields to ask for — a second copy in TypeScript, drifting
from the first the moment a requirement changed. They moved into the
region profile, where the slots already lived, and are served by
`GET /regions`. The rules read them too, so the form and the engine
cannot disagree about what a dossier needs.

Note the distinction the profile now carries: a slot's
`certificate_types` says what it **accepts**; `required_certificate_types`
says what the region **demands**. NAFDAC accepts a CEP and a CoA and
demands a CPP. EU's required lists are deliberately empty — "not
modelled", not "nothing required" — which preserves exactly the behaviour
the region-scoped rules had, and the UI says so rather than showing an
empty list that reads like a clean bill of health.

### The override: three gaps, one principle

The question that opened this was whether the override should be
admin-only. It should not, and the reasoning is worth keeping:

`UserRole.ADMIN` means "may manage accounts". Overriding a validation
error is a **documented deviation** — a quality decision. Reusing one bit
for both would make it mean two unrelated jobs, and the principle people
reach for ("who may approve") is really segregation of duties: the author
of the data should not be the sole approver of bypassing a check on it.
That needs a *project-scoped* role, not the account-administration bit.
With one user per dossier, an admin gate would only mean the same person
promotes themselves — theatre, which is worse than an honest open control
because it looks like a safeguard. The control is the audit trail: who,
why, when, reviewable, and named on every build that relied on it.

So: any project owner may record one, and three things changed around it.

1. **It can be withdrawn.** An override that can only be created and
   never retracted is not caution, it is pressure — the mistaken one
   stays forever, so the next gets logged with a vaguer reason "just in
   case". Withdrawal is a new fact on the same row, never a DELETE: the
   original decision and its reason survive it, which is the whole point.
2. **The reason has a floor** (20 characters). It is the entire control,
   and a free-text field with no floor collects "n/a".
3. **A build names what it waived.** A package assembled over a waived
   ERROR is byte-for-byte as convincing as one that passed cleanly.

On (3), a deliberate deviation from the plan: the plan said to render the
override list *into* the package. It is not written there. The ZIP is
what goes to the regulator, and an internal deviation record is the
applicant's own quality documentation, not submission content — shipping
it would be a different, unasked-for disclosure. It surfaces to the
person exporting instead.

### Two things that bit

**AmbiguousForeignKeysError.** Adding `withdrawn_by_id` gave
`validation_override` a second FK to `user`, and SQLAlchemy could no
longer infer which column `created_by` joins on. It announces itself at
*mapper configuration* time — the first query anywhere in the app — not
at the line that added the column, so the traceback points at an
unrelated test. Both relationships now name `foreign_keys` explicitly.

**Applicant ownership broke the seeds.** With `owner_id` NOT NULL, every
seed builder that created a bare `Applicant` stopped inserting.
`same_owner_as(product)` returns constructor kwargs rather than setting
an attribute, because which one to set depends on how the product got its
owner: a real seed holds an id, while one built for a model test holds a
transient `User` with no id until flush — passing `owner_id` there would
write None.

### Definition of done, met

`tests/test_module1_api.py` asserts it: a complete NAFDAC filing
assembled entirely over HTTP reaches `is_exportable` with no overrides
logged. The demo seed stays deliberately buggy — it is teaching material,
and making it pass would delete the lesson.

---

## P14 — ownership, roles, and the tests that were missing (2026-09-03)

Until now every authenticated user could read and write every product,
project and dossier in the database. That was a deliberate P02
simplification ("no roles/permissions yet; add scoping later if the
wizard needs it"), and the wizard needed it.

### Where the owner column belongs

The obvious place looks like Project — a project is what a person works
on. It is the wrong place. Every child resource (manufacturers, actives,
excipients, stability, packaging, specifications) hangs off **Product**,
and Project points at Product, so an owner on Project would leave the
entire product tree reachable by anyone who knew a product id. Worse, it
would let a stranger create their *own* Project against someone else's
Product and then walk in through the front door.

So `Product.owner_id` is the root, and every check joins through it:
`require_project_owner` goes Project → Product → owner, the child-router
factory checks the parent, and `create_project` verifies you own the
product you are naming. One column, checked in four shapes.

`ActiveIngredient` is the awkward case: it is one hop from Product and
owns the 3.2.S.4.1 specification rows. Rather than give it an owner
column of its own, `build_child_router` grew an `owner_via` argument
naming the relationship to walk, and raises `TypeError` at import time if
a non-Product parent is registered without one — a wiring mistake that
would otherwise ship as an open endpoint.

**404, never 403.** Someone else's project must be indistinguishable from
one that never existed. A 403 confirms the id is real, which is itself a
disclosure.

### Roles, and the first admin problem

`UserRole` (USER/ADMIN) gates `/admin/users` only — account management,
never a bypass of the ownership check. An admin reaches dossiers exactly
the way everyone else does. Two consequences worth writing down:

- The JWT carries a user id and no role claim. Baking the role in would
  let it go stale the moment an admin changed it, since nothing forces
  the holder to log in again; `GET /auth/me` looks it up fresh instead.
- There is no self-service path to ADMIN, so the first one cannot come
  from the API. `scripts/promote_admin.py` is that path — an operator
  action, not a feature the app exposes to itself.

`update_user` refuses to change the caller's own role or active flag: an
admin could otherwise demote the only admin there is and lock everyone
out of user management with no way back but psql.

### The migration gotcha

Adding a brand-new enum-typed column with `add_column` does **not** create
the Postgres type — every earlier enum here was born inside a
`create_table`, whose DDL creates the type as a side effect. Omitting the
explicit `role_enum.create(...)` fails with "type userrole does not
exist". The downgrade has the mirror problem: the type outlives the
column it served, so it needs an explicit, dialect-guarded drop or a
re-run of upgrade() fails with "type userrole already exists".

### What the audit found: the tests proved the wrong half

The suite went green through all of this. It was still green when two of
the ownership filters were deleted. Every API test asserts that an owner
*can* reach their own data, and the fixtures had simply been re-pointed at
the test user to keep them passing — nobody had ever asked whether a
second account was refused. A security boundary verified only by its happy
path is not verified.

`tests/test_ownership.py` is that missing half: a second registered
account probing all 17 project-scoped routes, every product-child
collection, the specification join, and the file-a-project-against-
someone-else's-product hole. Two things keep it from rotting:

- Every probe asserts the **domain message** ("Project not found"), not
  just the status. A mistyped URL returns 404 as well, so a status-only
  assertion passes just as happily against a route that does not exist.
- A mirror test replays every probe as the owner and asserts they never
  receive the *ownership* 404 — some of those routes legitimately 404 for
  their owner (validating an eCTD sequence that was never built), so the
  assertion is about which 404, not whether.

Verified by mutation: removing the filter in `require_project_owner` and
in `_get_product_or_404` turns 20 of the 55 red; restoring them returns
all 55 to green.

One probe (narrative `:generate`) skips its owner-side half — RAG
retrieval uses pgvector's `<=>`, which the SQLite fixture has no
equivalent for. The intruder half still runs there, because the gate is a
router dependency and answers before retrieval is reached.

### Two things the audit found, and closed the same day

- `scripts/seed_demo.py` attached its product to the placeholder account
  `attach_owner` invents for model tests, so after P14a the EXAMOX demo
  seeded fine and was invisible to every real login. It now takes an
  owner email, and — when called with no argument — falls back to the
  earliest account while *printing which one it chose*. Silently picking
  an owner is how you end up hunting for a demo project that seeded
  perfectly and belongs to someone else.
- `/kb/ingest` was gated on "any logged-in user" over a **global**
  knowledge base. Unlike a Product, the KB has no owner: one account's
  ingest changes the retrieved context behind everyone else's narrative
  generation. Its docstring had deferred a role check until a role
  existed, so P14b made this the honest fix — admin-only. Search stays
  open, because copyrighted pharmacopoeial text is refused at ingest by
  construction, leaving nothing there that needs an account to read.

### Known gap, still open

- Found in the same audit: a NAFDAC dossier cannot be
  completed through the API at all. Applicant, CPP certificate and
  declarations have models but no routers, so R13/R14/R16 block export
  permanently, and the only escape — validation overrides — has no
  frontend client. Clinical and batch formula have endpoints but no wizard
  step. That is the next phase's work.

---

## P13 — 3.2.S drug substance sections, and the first section that repeats (2026-08-14)

The platform built five sections, none of which had a drug-substance page
at all. 3.2.S was the obvious gap — and the interesting one, because it is
the first section that is **repeated per subject** rather than appearing
once.

### The design problem

Everything was keyed by a flat section number: the registry, the folder
map, the leaf filename, the narrative lookup, the eCTD section key. One
number, one document. 3.2.S breaks that: AMPICLOX owes two complete copies
of 3.2.S.1 and two of 3.2.S.4.1, and "3.2.S.1" alone no longer names a
document.

`app/templating/instances.py` is the seam. The registry stays a flat table
of specs (what sections *exist*); `expand_sections(project)` produces the
instances (what documents this project *owes*). Everything downstream
iterates instances.

The compatibility trick that avoided a data migration: an instance's key
equals the bare section number when the section doesn't repeat. Every
pre-P13 section keeps exactly the identity it had, so stored narratives
and persisted sequence leaves still resolve. Only repeated sections get
the `3.2.S.1-ampicillin` form.

### The DTD wrote most of the spec for us

Reading `ich-ectd-3-2.dtd` before designing was worth more than any
guessing:

```
<!ELEMENT m3-2-body-of-data (leaf*, m3-2-s-drug-substance*, ...)>
<!ELEMENT m3-2-s-drug-substance (leaf*, m3-2-s-1-general-information?, ...)>
<!ATTLIST m3-2-s-drug-substance  substance CDATA #REQUIRED
                                 manufacturer CDATA #REQUIRED>
```

Starred, so it repeats. Both attributes #REQUIRED, so a drug substance
**cannot be filed anonymously** — the spec refuses to let an assessor read
a specification without knowing whose it is and who made the material.
That handed us rule **R17** (every active must name its manufacturer),
caught at the data layer where the applicant can still fix it rather than
at a gateway. The seeds gained a real API-manufacturer site, distinct from
the finished-product site.

### The bug that would have been silent

`_Node`, the backbone tree helper, keyed children **by tag**. With a
repeating element that merges ampicillin's and cloxacillin's subtrees into
one — and because it is a merge rather than a crash, it produces a
**DTD-valid** backbone that files one substance's specification under the
other's name. Children are now keyed by `(tag, discriminator)`.

Every existing eCTD test used EXAMOX, which has one active, so all 36 of
them passed against the merged version. The regression test deliberately
uses AMPICLOX in the EU region and asserts two `m3-2-s-drug-substance`
elements with the right attributes and each substance's leaves under its
own element. **A test suite whose fixtures are all N=1 cannot see an N>1
bug.** That is the second time today the same lesson has come up.

### Specification: modelled as rows

Committed separately (see the previous entry). One point belongs here: the
relationship's `order_by` only applies when rows are **loaded from the
database**. An object built in memory — a seed, a test, an API create —
renders in insertion order. The rendered table has to be deterministic
either way, so the context builder sorts explicitly. The test that caught
this failed for a real reason, not a test-authoring mistake.

### Templates are generated now

`scripts/make_section_templates.py` builds both 3.2.S templates from
readable, diffable code. The older five stay hand-authored — converting
them is a separate behaviour-preserving change — but no new template
should be a binary blob. This was already the third time in one day that
editing a `.docx` meant surgery on a zip.

Gotcha worth keeping: docxtpl's `{%tr %}` row loop needs the tags in
**rows of their own**, above and below the data row. Putting `{%tr for %}`
and `{%tr endfor %}` in the first and last cells of the data row — which
reads like the obvious way — dies with `Encountered unknown tag 'endfor'`.
The hand-authored 3.2.P.1 template already used the tag-row form; matching
it was the fix.

### Known gaps

- Only 3.2.S.1 and 3.2.S.4.1 exist. S.2 (manufacture), S.3
  (characterisation), S.5–S.7 are more of the same now that the repeating
  mechanism works, and are deliberately not built yet.
- 3.2.P.5 (drug product specification) is the same table shape with a
  different owner. The `SpecificationTest` docstring says what to do when
  it arrives: widen with a nullable owner, don't guess today.

## Fix — the QOS showed only the first active ingredient (2026-08-14)

A defect flagged during P11c and cleared afterwards, before starting any
new phase. Worth reading for the scoping as much as the fix: **most of
what I thought was broken had already been fixed, and the one real bug
was somewhere I hadn't looked.**

### What was actually wrong

`render.py` built the 2.3 QOS chemical-structure image from
`project.product.apis[0].smiles` — the first active ingredient, full
stop. For AMPICLOX (ampicillin + cloxacillin) the Quality Overall
Summary rendered ampicillin's structural formula and silently omitted
cloxacillin's. No error, no placeholder, nothing on the page saying a
substance was missing — just a dossier describing half the product.

This is a regulatory error, not only a rendering one. **2.3.S (like
3.2.S) is repeated *per drug substance*.** A fixed-dose combination owes
the assessor one structural formula per active. "The structure of the
API" is a question that only has an answer for a single-API product, and
the code had quietly assumed every product was one.

### The fix

- `SectionSpec.structure_image_slot` → `structure_images_slot`, now
  bound to a **list**. The single-API case is a list of length one, so
  there is no special case to get wrong.
- `_build_structure_images` returns one `StructureSlot(name, image)` per
  API; the QOS template loops over them.
- Every structure is now **captioned with its substance name**, single-API
  included. With two formulas on a page an uncaptioned image is ambiguous,
  and an assessor cannot verify a structure they can't attach to a named
  substance.
- Degradation is **per substance**: if one active has a SMILES and the
  other doesn't, the first still gets its picture and only the second
  gets the placeholder. One missing field no longer blanks both.

The docx template itself had to change (`{{ structure }}` → a
`{%p for s in structures %}` loop), which meant editing the `.docx`
XML with python-docx rather than the source. **Note for next time:** the
templates are binary artifacts checked into the repo with no generating
script, so every template change is surgery on a zip. That's a real
maintenance cost we've now paid twice; worth reconsidering if it happens
again.

### The scoping lesson — I over-reported the problem

I had flagged this as "the `apis[0]` limitation", implying a data-model
gap. Grepping first showed that was wrong:

- Strength had **already** been moved from `Product` to
  `ActiveIngredient` back in P06, precisely so a second active had
  somewhere to put its own strength.
- R01 and R04 **already** loop over every API, and `AMPICLOX` exists as a
  seed fixture whose deliberate defect is on the *second* active — built
  specifically to prove those rules don't stop at `apis[0]`.
- The remaining `apis[0]` in `rules.py` is a guarded fallback (`if api is
  None and len(product.apis) == 1`), which is correct, not a bug.

So the data model and rule engine were fine. The template engine — built
in P04, *before* that P06 rework — was never revisited, and it was the
only layer still carrying the old single-API assumption. **A fix applied
at one layer doesn't propagate to layers written earlier against the old
shape.** Grep before scoping; the memory of a bug is not evidence.

### Follow-up — closing the gap: an FDC now builds end to end

Committed separately from the fix above, since it's a different concern.

AMPICLOX had only ever been exercised through the rule engine (P06) and
the template engine (P04). **No combination product had ever been run
through P07 assembly or a P08 CTD build** — so "the pipeline handles more
than one active" was an assumption, not a tested fact. That is exactly
the shape of gap that let the QOS bug survive until P11c.

It couldn't be tested as it stood: the fixture had no applicant, no
declarations, no CPP and no GMP status, so the P06 completeness rules
blocked assembly before anything interesting happened. Added those (plus
`specifications` on both actives, which R07 correctly demanded for *each*
API — another rule that turned out to be multi-API-aware already), and
the corrected variant now validates clean with **zero errors**.

`test_a_combination_product_builds_end_to_end` runs the whole chain —
render → DOCX→PDF → placement → TOC → manifest → zip — then opens the
assembled `2.3.pdf` out of the package and asserts that **both**
"Ampicillin" and "Cloxacillin" appear on the page, with no "Structure
not available" placeholder. It deliberately uses the clean variant and
passes **no overrides**, so it exercises the real validation gate rather
than bypassing it.

Result: no further bugs found. Nothing else in assembly or the CTD
builder branched on API count, as the grep had suggested. But the test
is the point — the assumption is now checked on every run instead of
being re-verified by hand whenever someone remembers to wonder.

---

## P11c — Narrative review, validation viewer, build + download (P11 complete)

The last slice, and the one that closes the loop the platform promises:
empty project → captured data → reviewed narrative → validation → a
downloaded package, entirely through the UI.

- **Two gaps the frontend exposed, neither of which had come up while the
  API only ever served tests:**
  - Nothing told a client *which sections exist* or which narrative slots
    each offers. Added `GET /sections`, derived from
    `app.templating.registry.SECTIONS` — same "derive, never duplicate"
    reasoning as `GET /enums` in P11b. Without it, registering a new
    section (P04's open/closed payoff, which the QOS interlude exercised
    with zero code changes) would silently fail to appear in the review
    UI.
  - P08/P09 stored their zips and returned a `storage_key`, but **nothing
    could hand those bytes to a human** — "build & download" had no
    download. Added `GET /projects/{id}/artifacts?key=…`.
- **Authorization, not validation, on the artifact download.** `key` is
  client-supplied and `StorageClient.get` will fetch whatever it is
  given — so without a check, a caller could pass another project's key,
  or any object in the bucket, and read it. The endpoint requires the key
  to start with `projects/{project_id}/`, which every builder already
  guarantees. Tested explicitly: another project's key and a bare
  `kb/…` path both 403, an unbuilt key 404s rather than 500s, and the
  endpoint refuses anonymous callers.
- **The narrative review UI enforces the gate by displaying it, not by
  re-implementing it.** A draft is marked "awaiting review" until a human
  approves or edits it, because on the backend only those two actions set
  `final_text`, and only `final_text` reaches a rendered document. The
  panel also shows the retrieved sources and any guardrail warnings, so
  "everything the LLM writes is reviewable" (AGENTS.md §5) is something
  the screen actually demonstrates.
- **Real bug, caught only by the browser: a status enum compared in the
  wrong case.** The hand-written TypeScript union declared
  `"PENDING" | "APPROVED" | "EDITED"`, but Pydantic serializes the enum's
  *value*, which is lowercase — so `status === "APPROVED"` was never true
  and **an approved narrative displayed as "awaiting review" forever**.
  In a review workflow that is not cosmetic: it hides a human sign-off
  and invites the reviewer to approve the same draft repeatedly. TypeScript
  couldn't help — the literals were internally consistent, just wrong
  about the wire format. This is exactly the drift `/enums` and
  `/sections` exist to prevent, in the one place a type was hand-written
  instead of derived. Fixed, with a unit test pinning the lowercase wire
  values.
- **Region awareness is driven by the project's region, not a second
  opinion in the UI:** NAFDAC is offered the CTD builder only (its filing
  genuinely has no XML backbone), FDA/EU the eCTD sequence builder.
  Builds are deliberately *not* pre-gated in the component — P07 already
  refuses to assemble when validation has unresolved errors and the API
  answers 409, so the UI surfaces that message instead of duplicating the
  rule (which also keeps it honest when a human has logged an override).
- **Downloads fetch-then-save rather than pointing a link at the
  endpoint.** A plain `<a href>` can't carry an Authorization header, so
  the obvious version would need the token in the query string — where it
  leaks into server logs, browser history and referrers. Fetching with
  the normal header and handing the browser a blob keeps the credential
  where it belongs.
- **Playwright happy-path** (`frontend/e2e/`) drives the real backend, on
  purpose: nearly every bug this whole phase surfaced — missing CORS, an
  API bound to the wrong IP stack, "Add stability studie", the status-case
  bug — was invisible to unit tests by construction. A mocked version
  would have sailed through all of them.
- **Test hygiene problem found and fixed in the test itself:** the first
  version borrowed the EXAMOX seed and overrode its validation rules to
  get a build through. That permanently mutated shared demo data
  (overrides have no DELETE endpoint, so they accumulated on every run)
  and destroyed the seed's teaching value — it is *deliberately* buggy,
  and making it exportable removes the thing it demonstrates. Rewritten
  to create, override, and delete its own project. A test that needs
  mutable state should own that state.
- 7 new backend tests (205 → 212), 3 new frontend unit tests (16 → 19),
  and 1 end-to-end spec.

---

## Working conventions — build log made a standing rule (2026-08-13)

Previously the log was an end-of-phase chore (AGENTS.md §8). It is now a
cross-cutting rule in §5, triggered by *solving a problem* as much as by
finishing a phase, and this file now states its own contract at the top.
Two problems solved earlier in this session had gone unrecorded under the
old convention and are captured here for completeness:

- **`pkill -f "<pattern>"` kills the command that contains the pattern —
  including the very shell running it.** Restarting a dev server with
  `pkill -f "next start"; npm run start` repeatedly killed the server it
  had just started, which looked like the server crashing on boot. Kill by
  PID (`ss -ltnp` → `kill <pid>`) instead, in a separate step from the
  restart.
- **`NEXT_PUBLIC_*` env vars are inlined at build time, not read at
  runtime.** Changing `.env.local` and restarting `next start` changes
  nothing; the old value is baked into the bundle. Re-run `npm run build`.
  Cost real time when the API base URL appeared not to update.

---

## P11b — Frontend: the Product Information Wizard (second slice of P11)

The screen that carries the product's whole thesis: it captures
structured **data** and never asks anyone to upload a finished dossier.
Seven steps — Product → Manufacturers → Active ingredients → Excipients →
Packaging → Stability → create the Project.

- **New `GET /enums` endpoint, rather than hard-coding the vocabularies
  in TypeScript.** These enums *are* the regulatory control — a Postgres
  ENUM physically cannot store a value that isn't on the approved list
  (`app/models/enums.py`). A second hand-maintained copy in the UI is
  exactly how the approved list and the offered list drift apart, and the
  dangerous failure isn't "the UI offered something the DB rejects" (loud,
  harmless) but "the UI quietly offered a stale vocabulary a regulator
  later queries". Adding a dosage form stays a one-line change to
  `enums.py`; the wizard picks it up with no frontend edit. Four tests,
  written so they'd fail on drift rather than needing an update when a
  38th dosage form appears.
- **The wizard is driven by field specs (`lib/wizard-steps.ts`), not six
  bespoke forms** — mirroring the backend, which builds all six
  Product-child routers from one factory
  (`app/api/routers/product_children.py`) precisely because they are the
  same resource shape with different fields. Adding a field is one line;
  adding a collection is one entry.
- **Saves as you go**, because that's how the API is actually shaped: step
  1 creates the Product, every later step attaches children to that id. A
  half-finished product is a legitimate state — P06's completeness rules
  decide whether it can be *exported*, not the form. Re-entering step 1
  after going back doesn't create a second Product.
- **Real bug caught by driving a real browser, not by types or lint:**
  the add-button label was derived with `title.replace(/s$/, "")`, which
  renders "Stability studies" as **"Add stability studie"**. English
  plurals aren't regex-able, so the singular is now written out as data
  (`addLabel`) like everything else in the spec, with a regression test.
  A good reminder that a clean typecheck says nothing about what the
  screen actually reads like.
- **Verified end-to-end in a browser, including the case the data model
  was reshaped for:** the run adds *two* active ingredients with their own
  strengths, and the created project's detail page renders
  `Ampicillin 250 mg + Cloxacillin 250 mg` — the combination-product
  support from the pre-P06 interlude, now reachable through the UI. The
  readiness report then fires **R07 once per active ingredient**, which is
  the multi-API fix (no more `apis[0]` shortcuts) proving itself through
  the full stack.
- Field help text names the rule each value feeds (shelf life → R05,
  GMP status → R08, specifications → R07, salt factor → R04), so the form
  teaches *why* a field matters rather than just demanding it.
- 3 new frontend tests (13 → 16) and 4 new backend tests (201 → 205).

---

## P11a — Frontend: scaffold, auth, dashboard (first slice of P11)

P11 is the biggest phase in the plan (8 tasks), so it's being built in
three runnable slices rather than one unreviewable drop. This is slice
one: a user can sign in and see a real project's readiness report.

Next.js 16.3 (App Router) + TypeScript + Tailwind 4 in `frontend/`, per
AGENTS.md §3. The scaffold ships its own `AGENTS.md` warning that this
Next version differs from training data — read
`node_modules/next/dist/docs/` first, which is where `PageProps<'/route'>`
/ `LayoutProps<'/'>` (route-aware type helpers, params arriving as a
Promise) came from rather than guesswork.

- **Real bug this phase existed to find: the backend had no CORS
  middleware at all.** Every one of the 198 backend tests passed while the
  API was, in fact, unreachable from any browser — httpx doesn't enforce
  the same-origin policy, so nothing in the suite could have caught it.
  Only driving a real browser at it surfaced the problem. Fixed with
  `CORSMiddleware` + a configurable `CORS_ALLOW_ORIGINS` allowlist
  (explicitly never `*`: this is a bearer-token API, and a wildcard origin
  is exactly what lets any site a logged-in user visits call it with their
  credentials). `tests/test_cors.py` locks in the one thing httpx *can*
  check — that preflight responses carry the right headers, and that an
  unlisted origin gets no grant.
- **Two misleading symptoms worth remembering, both of which look like
  CORS and aren't:** (1) if `localhost` resolves to `::1` first and the API
  is bound only to `127.0.0.1`, the browser's connection is refused and
  reported as "No 'Access-Control-Allow-Origin' header"; `curl` hides this
  by falling back to IPv4. (2) any endpoint returning **500** produces the
  same message, because FastAPI's CORS middleware doesn't attach headers
  to unhandled-exception responses — the actual cause the second time was
  simply Postgres being down. Both documented in `frontend/README.md`, so
  the next person checks the API log before touching CORS config.
- **`useSyncExternalStore` for auth, not `useState` + a mount effect.**
  The first version read localStorage in an effect and called setState —
  which `react-hooks/set-state-in-effect` correctly flags as a cascading
  render. localStorage *is* an external store, so the purpose-built hook
  is the right tool; it also gives cross-tab logout for free (the
  `storage` event fires in other tabs). The server snapshot returns
  `undefined` while the client snapshot returns `string | null`, which
  keeps "not read yet" distinct from "signed out" — collapsing those two
  makes every guarded page flash the login screen for a frame.
- **Data is fetched in Client Components, deliberately.** The token lives
  in localStorage, which a Server Component cannot read; going
  server-side would mean an httpOnly cookie plus proxying every request
  through Next's server, buying nothing (the backend already enforces
  auth) and adding a second place for auth logic to drift. Reasoning is
  recorded at the top of `lib/api.ts` along with what would have to change
  to revisit it.
- **One small backend consistency fix:** `FindingRead` (P06's `/readiness`
  response) gained the `source` field P10 added to `Finding`, defaulted so
  nothing else changed. The UI now renders one shape of finding
  everywhere instead of two.
- **Severity styling encodes a real distinction, not decoration:** ERROR
  is the only severity that blocks an export, so it's the only red one;
  ADVISORY (the AI reviewer) is visually distinct from every deterministic
  severity so nobody mistakes a suggestion for a finding. A Vitest case
  asserts those two never render identically.
- **Dev-data note (not a code bug, but worth knowing):** migration
  `bf6ef09c07bf` moved `strength_value`/`strength_unit` from `Product` to
  `ActiveIngredient` with no data backfill, so any row seeded before
  2026-07-25 shows a blank strength. Harmless in a dev database; in
  production that same shape of migration would silently blank a value
  regulators cross-check (it's exactly what R01 exists to verify). Future
  column moves should carry an `op.execute` backfill between the add and
  the drop.
- 13 frontend tests (Vitest) + 3 new backend CORS tests (198 → 201).
  Verified end-to-end in a real browser: sign in → project list →
  readiness report → reload (session survives) → sign out, no console
  errors.

---

## P10 — eCTD Validation (mechanical checks + validator adapter + AI reviewer)

Validates a BUILT sequence's zip artifact, merging four independent
layers into one consolidated report with per-finding provenance.

- **The core distinction this phase exists to keep straight:** P06
  validates the *data* before anything is rendered; P10's mechanical
  checks validate the *built artifact* afterwards. P06 can pass while the
  package is still broken (a storage bug, corruption at rest, a bug in
  P09 itself) -- which is exactly why this layer re-reads the actual zip
  bytes instead of trusting that a clean P06 implies a clean package.
  Proved with a test that corrupts the stored zip *after* a successful
  build and confirms M03 catches it.
- **"Merge 4 report types" became "concatenate 4 lists"** by adding one
  `source: str` field to the existing `Finding` (defaulted to
  `"data-rule"`, so all 16 existing P06 rules needed zero changes)
  instead of inventing a parallel report type. The consolidated report
  is literally P06's `Report` with more findings in it.
- **`Severity.ADVISORY` makes "the AI reviewer never gates" structural,
  not a convention.** `Report.errors()`/`is_exportable()` only ever look
  at ERROR, so an advisory finding is *mechanically incapable* of
  blocking an export -- no caller has to remember to filter it out. Same
  "let the type system prove it" instinct as P06's FK-over-comment
  choice. AGENTS.md's "never let the AI reviewer override deterministic
  checks" is now enforced by construction.
- **Twelve mechanical checks (M01-M12)** across six concerns: DTD
  re-validation, checksum integrity (per-leaf + `index-md5.txt`), href
  resolution + orphan detection, lifecycle integrity, PDF specs, and
  required-section presence. Every one has a deliberately-corrupted
  fixture proving it catches its fault, plus a clean case proving it
  doesn't false-positive.
- **Lifecycle integrity needs MORE than the sequence being validated:**
  a `modified-file` reference is only verifiable by fetching the PRIOR
  sequence's own built zip from storage and confirming the target leaf
  really exists there with a matching ID and path. A `replace` pointing
  at a leaf that was never really there is the reference doc's stated #1
  real-world eCTD rejection cause.
- **Honest about what it cannot check.** PDF font-embedding is NOT
  verified -- flagged as an explicit documented gap rather than quietly
  omitted. Text-searchability is checked via a stated PROXY (non-empty
  extracted text) and reported as WARNING, not ERROR, because that's
  what a proxy earns.
- **`NullExternalValidator` emits a real ADVISORY finding, not silence.**
  AGENTS.md's "never claim gateway-readiness from internal checks alone"
  has to be something the REPORT SAYS -- a caller who never reads the
  module docstring would otherwise have no way to know the external layer
  didn't run. The `ExternalValidator` interface is the 5th repetition of
  this project's provider-abstraction shape (LLM / embedding / storage /
  BackboneBuilder / now this), so a real eValidator-class tool drops in
  by writing an adapter and flipping one config value.
- **The AI reviewer degrades instead of exploding** (added after the
  main build, on noticing the gap): a dead LLM, missing key, or rate
  limit becomes a visible `AI99` advisory rather than an exception that
  takes down the deterministic report a human actually needs.
  "Advisory-only" has to mean the layer can't hurt you when it FAILS,
  not merely when it disagrees. It also reads P05's already-audited
  `final_text` rather than re-extracting text from the built PDF --
  strictly better data, reached the easier way.
- **New `POST /projects/{id}/validate/ectd?sequence_id=...`**, sibling
  to P09's build endpoint; 404 on an unbuilt sequence (distinct from
  "validation found problems", which is a 200 with findings).
- 24 new tests (174 -> 198 total): 15 pure-function mechanical/adapter
  tests, 6 integration tests over real built packages (one self-skipping
  without Postgres, since the AI reviewer's KB retrieval needs pgvector),
  and 3 API tests on the new endpoint.

---

## P09 — eCTD v3.2.2 XML Backbone Builder (EU region)

Wraps P07's leaf inventory in a real, DTD-valid eCTD v3.2.2 transport
layer: sequenced folders, ICH `index.xml`, the EU regional backbone
(`eu-regional.xml`), `index-md5.txt`, per-leaf MD5 checksums, and
lifecycle operation attributes (`new`/`replace`/`delete`). FDA is not
built -- see the scope note below.

- **Real DTDs, not invented ones.** Fetched the official EMA eSubmission
  "EU Module 1" utility package (`reference/ectd_dtd/README.md` has the
  exact source/date) -- it bundles the genuine `ich-ectd-3-2.dtd`
  *inside* the EU package (EU's DTD imports it), plus `eu-regional.dtd`,
  `eu-envelope.mod`, `eu-leaf.mod`, and both stylesheets. Both backbones
  are validated in-process via `lxml.etree.DTD` against these real files,
  not a hand-approximated schema -- same "real source, not a paraphrase"
  principle as P03's ICH guideline ingestion.
- **Confirmed from the real DTD, not assumed:** the ICH backbone's own
  M1 element (`m1-administrative-information-and-prescribing-
  information`) is a flat, structure-less `(leaf*)` bag -- Module 1's
  real hierarchy (`m1-0-cover`, `m1-2-form`, ...) lives entirely in the
  *regional* backbone. `app/ectd/index_xml.py` never touches Module 1 at
  all; `app/ectd/regional.py` owns it completely.
- **lxml namespace gotcha, caught by testing before building further on
  it:** tried literal colon-in-string attribute names first
  (`el.set("xlink:href", ...)`) to match the DTD's namespace-unaware
  declarations -- lxml rejects this outright. Verified empirically that
  lxml's *real* namespace API (`nsmap=`, Clark notation) round-trips
  through `tostring()`/`fromstring()` into textually identical output and
  validates cleanly; libxml2's DTD validator matches the serialized
  qualified name, not the construction method. Wrong assumption caught
  before it became load-bearing, not after.
- **A real, documented quirk of the ICH DTD itself, reproduced verbatim:**
  its `#FIXED` xlink namespace URI is misspelled `http://www.w3c.org/1999/
  xlink` (should be w3.org). "Fixing" the typo would make our own output
  DTD-invalid against the DTD we're validating against.
- **`SequenceLeaf` (new model + migration `8434fdfbdb4f`):** persists each
  sequence's full *cumulative* dossier state (not just that sequence's own
  backbone delta), so the lifecycle resolver has something complete to
  diff against even when a document hasn't changed in several sequences
  running. Getting this right took a real design correction mid-build:
  persisting only what a sequence's own XML restated would silently lose
  history the first time a sequence went by without touching a given
  document.
- **`app/ectd/lifecycle.py` -- the highest-risk logic, per the reference
  doc.** An unchanged leaf is entirely OMITTED from a sequence's own
  backbone (real eCTD semantics: a reviewer's tool replays every sequence,
  so a leaf nobody mentions is still whatever the last sequence that DID
  mention it said) -- naive designs commonly restate everything every
  time instead. Verified three sequences deep (new -> unchanged-carried-
  forward -> replace -> delete), not just a two-sequence happy path.
- **Real regulatory nuance caught by DTD validation, not by inspection:**
  the EU regional DTD marks `m1-0-cover` as the one `m1-eu` child that's
  mandatory (no `?`), because a real cover letter is per-submission
  correspondence that's always fresh. Our cover-letter rendering doesn't
  vary by sequence number yet, so an unchanged-checksum cover letter got
  correctly omitted by the lifecycle resolver -- and then failed DTD
  validation the moment a second sequence was actually tested, not before.
  Fixed by always emitting `m1-0-cover` (with an empty `<specific>` when
  there's nothing new), which the DTD's own content model explicitly
  permits. Threading `Sequence` into P04's renderer to make cover letters
  genuinely resequence-aware is the "correct" fix but out of this phase's
  scope -- flagged, not silently worked around.
- **Deterministic leaf `ID` scheme** (`ID-<section-slug>-<sequence-
  number>`) instead of random/UUID: golden-fixture byte-stability rules
  out randomness, and the lifecycle resolver needs to compute what a
  leaf's ID *was* in a prior sequence purely from `section_key` + that
  sequence's number, with no lookup table.
- **`BackboneBuilder` interface** (`app/ectd/backbone.py`), one
  implementation (`V322BackboneBuilder`) today -- so P12's
  `V4RpsBackboneBuilder` slots in later without touching assembly,
  templating, validation, or `app/ectd/build.py`'s orchestration, per the
  reference doc's explicit ask.
- **Each sequence packages as its own self-contained zip**
  (`projects/{id}/ectd/<number>.zip`), not one combined archive --
  matches the reference doc's own physical-structure diagram (sequences
  are sibling directories); `modified-file`'s relative `../0000/...`
  paths are only meaningful once sequences sit next to each other on
  disk, same as a real gateway delivery.
- **New `POST /projects/{id}/build/ectd?sequence_id=...`** -- takes an
  already-created `Sequence` (via P02's existing auto-numbering endpoint)
  rather than inventing a second numbering path; 201 + build report,
  409 on unresolved validation, 404 on missing project/sequence.
- **Scope call, made explicit rather than silently decided:** built EU
  only, not FDA -- building both regional DTDs/envelopes well in one pass
  would blow past "minimum viable backbone" (per the reference doc's own
  scoping). FDA's `us-regional.dtd` and envelope controlled vocabulary
  are unbuilt; `V322BackboneBuilder` raises `NotImplementedError` rather
  than silently producing something DTD-invalid if ever asked for FDA.
  User's explicit choice over FDA when asked directly.
- **Also a documented MVP simplification, not a gap discovered later:**
  the EU envelope's agency/procedure/country (`app/ectd/regional.py`'s
  `_AGENCY_CODE`/`_PROCEDURE_TYPE`/`_ENVELOPE_COUNTRY` constants) are
  baked into the builder rather than per-`Project` fields -- real EU
  submissions choose a member state or EMA-centralised per project, which
  `Project` doesn't model yet. Same category of edge as P04's QOS
  deferral and P08's labeling-artwork deferral.
- 19 new tests (`test_ectd_build.py`, `test_ectd_api.py`) — pure DTD/
  lifecycle unit tests plus two-sequence-deep integration tests against a
  real (throwaway SQLite) EXAMOX project with `region` overridden to EU.

---

## P08 — CTD / NAPAMS Folder + TOC Builder (first shippable deliverable)

Assembles the P07 leaf inventory plus the new Module 1 documents (cover
letter, registration form, certificates, declarations) into an actual
NAFDAC CTD folder tree, with a generated TOC and a manifest, zipped for
upload to NAPAMS. Per nafdac-vs-fda-ema-scope.md, this needs no XML
backbone at all -- a structured folder of PDFs plus a TOC genuinely is a
complete, submittable CTD.

- **New `app/ctd/` package**, split exactly along the region-varies /
  region-doesn't line from nafdac-vs-fda-ema-scope.md: `structure.py` is a
  plain hardcoded Module 2-5 folder map (identical across NAFDAC/FDA/EMA),
  while `region_profiles.py` holds NAFDAC's Module 1 slot list as data,
  not code branches. Adding FDA/EU later is "write a new `RegionProfile`,"
  not "add an if-branch to the builder" -- the same design principle P06's
  `regions=[...]` rule filtering already established.
- **Folder naming reuses the eCTD-style convention** from
  reference/ectd-backbone-architecture.md (`m3/32-body-data/...`) even
  though NAFDAC needs no XML backbone -- costs nothing now, and means
  P09's eCTD builder can point at the same physical files later instead of
  re-deriving a second folder scheme.
- **`build_ctd_package` (`app/ctd/build.py`) reuses P07's gate wholesale**:
  it calls `assemble_project` and lets `AssemblyBlockedError` propagate
  unchanged, rather than re-checking validation itself -- AGENTS.md §5's
  "validation is a gate" stays true in exactly one place.
- **Certificates and declarations get converted to PDF too**, through the
  same `convert_docx_to_pdf` P07 built -- a submission package that mixed
  PDF leaves with stray .docx placeholders would look broken, even though
  the *content* of those placeholders is intentionally a stand-in.
- **Idempotent by construction, not by accident**: `zipfile` stamps each
  entry with the current wall-clock time by default, which would make
  every build of the same project unique -- the exact same class of bug
  P07 found in the PDF `/CreationDate`. Fixed by design this time (pinned
  `ZipInfo.date_time` to 1980-01-01, zip's own floor, plus sorted entry
  order) instead of being caught by a failing byte-identity test, since
  the lesson was already on file.
- **`manifest.json`** lists every OTHER file's path + MD5 -- computed
  before it's added to the file set itself, since a manifest entry for its
  own file would need a hash of something that doesn't exist yet.
  Deliberately holds no "generated at" timestamp, for the same determinism
  reason as the fixed ZIP date.
- **`toc.pdf`** is generated from the exact same path/title dict the
  builder just assembled, not a separate query -- it cannot list a
  document that isn't really in the package, or omit one that is.
- **API**: `POST /projects/{id}/build/ctd`, 201 with the manifest on
  success, 409 (not 500) when validation is unresolved.
- **Concept to revisit:** Module 1 here only covers what has a real data
  model behind it (cover letter, registration form, certificates,
  declarations) -- product labeling/artwork mock-ups (dossier-anatomy.md's
  fuller Module 1 list) aren't modeled yet and aren't part of this
  package. Same "scope to what the data model actually supports" call
  P04 made for 3.2.P.5.1/QOS back when those didn't exist either.

12 new tests (9 `test_ctd_build.py`, 3 `test_ctd_api.py`); 145 passing
overall. Full suite runtime grew to ~2m20s -- each CTD build now runs
~9 LibreOffice conversions (5 sections + 1 certificate + 2 declarations +
1 TOC), on top of P07's own conversions.

---

## Interlude before P08 — Module 1 data model (Applicant, Declaration)

A direct request ("let's build the data-model entities and everything Module 1
will require before we proceed") surfaced a real gap: nothing in the model
captured *who* is filing (dossier-anatomy.md's opening Module 1 question) --
only *what* (Product) and *to whom* (Project.region).

- **`Applicant`** (new model, master data like `Manufacturer`): company,
  address, contact, authorized representative. `Project.applicant_id` FK,
  nullable -- same "row can be incomplete, P06 catches it" treatment as
  `shelf_life_months`, not a schema-level NOT NULL.
- **`Declaration`** (new model, project-scoped): Power of Attorney,
  Declaration of Authenticity, GMP Compliance Undertaking. Deliberately NOT
  folded into `CertificateType` -- a Certificate's content is unknown to us
  (a regulator/lab issues it); a Declaration's content is fully generatable
  from data on file, only missing a wet signature and (for some types) a
  notary's seal. That's a different placeholder ("SIGN AND NOTARIZE", not
  "REPLACE THIS FILE") and a different completeness check (signed/notarized
  flags, not "does a row exist"). `DECLARATIONS_REQUIRING_NOTARIZATION` in
  `enums.py` is the single source of truth both the placeholder text
  (`app/templating/declarations.py`) and rule R15 read, so they can't drift.
- **`CertificateType`** gained `TRADEMARK` and `MANUFACTURING_LICENCE` --
  both are exactly the "third-party document, not yet obtained" shape
  `Certificate` already models, so no new entity was needed there.
- **New section `1.2`** (Application/Registration Form): `narrative_slots=[]`
  -- unlike the cover letter, every fact here is already structured data
  (applicant, product, region), so there's nothing for P05's LLM to draft. A
  concrete example that not every Module 1 document needs narrative prose.
- **Rules R14-R16**: R14 (NAFDAC-only) requires an `Applicant` on file. R15
  (universal) requires any attached `Declaration` to be signed (ERROR) and
  notarized where required (WARNING -- a nudge, not a hard block, since this
  engine can't independently verify the real notarization requirement). R16
  (NAFDAC-only) requires the Power of Attorney and Declaration of
  Authenticity specifically to be present at all -- distinct from R15, which
  only checks whatever's already attached.
- **Migration `fed49611d433`**: new `applicant`/`declaration` tables, hand-
  written `ALTER TYPE certificatetype ADD VALUE` (Postgres-only, same
  pattern as the dosage-form expansion -- autogenerate never detects added
  enum labels), and `project.applicant_id` added via `batch_alter_table`
  (SQLite has no `ALTER TABLE ADD CONSTRAINT`, same fix as the earlier
  combination-product migration). Verified upgrade *and* downgrade against a
  throwaway SQLite file before trusting it.
- **Seed data**: EXAMOX and LAMOX both got a real `Applicant` plus signed
  (and, for the POA, notarized) declarations -- added unconditionally
  regardless of the buggy/corrected narrative variant, same treatment as
  their existing CPP certificate, so the existing "clean project passes
  validation" tests kept passing under the new rules. AMPICLOX was
  deliberately left untouched -- its tests only ever check R01/R04
  specifically, never full exportability, so there was no gap to close and
  touching it risked an unrelated diff.
- **Concept to revisit:** the "signature/notarization required" placeholder
  content (`declarations.py`) makes a judgment call about which declaration
  types need notarization for a *NAFDAC* filing specifically -- a real
  submission should confirm this against current NAFDAC guidance, same
  "verify before trusting" caveat as R11's pharmacopoeia-edition reminder.

14 new tests (`test_module1.py`); 133 passing overall.

---

## P07 — Document Assembly + PDF (DOCX->PDF, bookmarks, granular leaves)

Converts P04's rendered `.docx` sections into eCTD-grade PDFs: text-
searchable, bookmarked, byte-deterministic, one leaf per section.

- **New system dependency: LibreOffice headless**, installed via apt in
  both this environment and `backend/Dockerfile` + CI (no Python library
  converts a real DOCX to PDF faithfully — LibreOffice's own layout
  engine is what actually does it). Flagged explicitly before installing,
  same as RDKit earlier — a real, non-trivial dependency, not a free
  addition.
- **How byte-stable PDFs were actually achieved** (the phase's own
  required detail): verified empirically, not assumed, that converting
  the same `.docx` twice gives two *different* PDFs by default (confirmed
  differing MD5s) — `soffice` embeds a wall-clock `/CreationDate` and a
  freshly-randomized `/ID` on every run. `app/assembly/pdf.py` normalizes
  both with `pypdf` after conversion: pins `/CreationDate`/`/ModDate` to a
  fixed constant, then lets `pypdf` recompute `/ID` from a checksum of
  the (now-normalized) PDF structure itself -- content-derived, not
  time-based, so identical content always yields an identical ID.
  Re-verified after the fix: two conversions now produce byte-identical
  output, in the same process and across separate process invocations.
- **Bookmarks are set from known data, not detected**: rather than
  scanning the rendered PDF for heading-sized text, `convert_docx_to_pdf`
  takes an explicit `bookmark_title` (the caller already knows it from
  `SectionSpec.title`). Turned out LibreOffice *also* auto-generates a
  bookmark from the docx's own "Heading" paragraph style, which produced
  a confusing near-duplicate outline entry — fixed by appending with
  `import_outline=False` so only the authoritative, guaranteed one
  survives.
- **`app/assembly/assemble.py`**: the orchestrator. Iterates every
  registered `SectionSpec`, pulls whatever narrative is already approved
  (P05), renders (P04), converts to a leaf PDF, and returns a leaf
  inventory (`{section, title, storage_path, md5, filename}`) — the
  shared input P08/P09 will consume later. Granularity (no mega-PDF) is
  structural, not a rule to remember: the loop writes one leaf per
  section by construction, so there's no code path that could concatenate
  two sections together.
- **Gated on P06's validation report**: refuses to produce anything at
  all — not even a partial manifest — if `report.is_exportable
  (overridden_rule_ids)` is `False`.
- **A real bug, caught by testing the negative case, not just the happy
  path:** the orchestrator initially never imported `app.validation.
  rules` (only `app.validation.engine.run_all`) — since `@rule` decorators
  only register themselves as a side effect of that module being
  imported somewhere, the rule registry was silently empty and a buggy
  project sailed through assembly with zero findings. Caught immediately
  by testing that a known-buggy project actually gets blocked, not by
  assuming the happy-path test passing meant the gate worked. Same
  "explicit registration import" footgun the narrative router already
  had to guard against — worth remembering as a recurring shape of bug
  in this codebase's rule-registration pattern.
- **Concept to revisit:** LibreOffice conversion is synchronous/blocking
  and takes ~1-2s per section; running it directly inside an async
  request handler (as the orchestrator currently does) blocks the event
  loop. Fine for this phase's scope (correctness over performance), but
  the P07 prompt itself flags "run in its own container/process if
  needed" as a follow-up, not something solved here.

13 new tests (6 pdf.py, 7 assemble.py); 129 passing overall. Full suite
runtime grew from ~14s to ~55s, almost entirely LibreOffice conversion —
a real, deliberate tradeoff for testing the actual conversion rather than
mocking it.

---

## Interlude before P07 — expand DosageForm (8 -> 37 members)

A direct question ("does this project capture every drug dosage form?")
got an honest "no" -- the enum had exactly 8 members, scoped to what the
existing capsule-only demo products needed, not a real catalog.

- Expanded `DosageForm` from 8 to 37 members, grouped by route/category
  (oral solid, oral liquid, parenteral, topical, ophthalmic/otic/nasal,
  rectal/vaginal, inhalation) -- the grouping mirrors how a CTD reviewer
  actually thinks about Module 3.2.P content. Modified-release/enteric-
  coated tablet variants got their own members rather than folding into
  a generic "tablet", since their dissolution specs and stability
  considerations genuinely differ.
- **First hand-written (non-autogenerated) migration in this project:**
  alembic's autogenerate doesn't detect added Postgres enum labels at
  all, so `1c06948fcf0b` is `ALTER TYPE dosageform ADD VALUE IF NOT
  EXISTS ...` per new member, guarded to Postgres only (SQLite has no
  ALTER TYPE, and every test in this suite builds tables via `Base.
  metadata.create_all()`, which always reflects the current Python enum
  class directly -- only a real, already-migrated Postgres database has
  a `dosageform` type frozen at its old 8 values). Verified by hand
  against both SQLite and a throwaway real Postgres database (the enum
  actually has all 37 labels afterward), since this is exactly the kind
  of migration autogenerate can't check for you.
- **Downgrade is a deliberate no-op**: Postgres has no `ALTER TYPE ...
  DROP VALUE` -- removing a label requires rebuilding the whole type.
  Leaving unused labels in place during a downgrade is harmless; the
  `product` table and its `dosage_form` column are fully removed by an
  earlier migration's downgrade when rolling back past this one anyway.
- **R02's `_FORM_WORDS` mapping expanded alongside the enum** (tablet,
  capsule, syrup, suspension, injection, infusion, cream, ointment, gel,
  lotion, suppository, pessary, lozenge, granules, elixir, patch) --
  deliberately excluding ambiguous words ("drops" alone could mean eye or
  ear); a wrong word-to-form mapping would make R02 flag mismatches that
  aren't real, which is worse than missing one.
- 3 new tests: every dosage form round-trips through a real database,
  and R02 correctly catches (and doesn't false-positive on) a mismatch
  involving one of the new forms specifically -- proving the expansion
  is actually wired into the rule engine, not just sitting in the enum.

116 tests passing.

---

## P06 — Deterministic Validation / Rule Engine (13 rules, 113 tests)

Graduated the pre-P00 vertical-slice prototype (`app/validation/engine.py` +
R01-R06) into the real thing: region-aware rule filtering, a logged
human-override escape hatch, 7 new rules closing categories R01-R06 didn't
touch, and `/projects/{id}/readiness` + `/validation-overrides` replacing
the P02 stub.

- **`Report.is_exportable`/`.errors` changed from properties to methods**
  taking an optional `frozenset[str]` of overridden rule ids — a small,
  deliberate breaking change (touched ~4 existing call sites) rather than
  bolting on a second parallel method, since "exportable with no
  overrides" is just the default-argument case of the real question.
- **Region filtering lives in `run_all`, never in a rule body:**
  `@rule(rule_id, regions=[...])` stores which regions a rule applies to;
  the engine skips it outright for a non-matching project. R13 (NAFDAC-only
  CPP certificate check) is the concrete proof — same rule registration
  pattern every other rule uses, just with one extra argument.
- **`ValidationOverride` is a durable, DB-backed row, not a flag on
  `Finding`:** findings are recomputed fresh on every `run_all` call and
  never persisted, so there's nothing to flag — an override is a
  standing decision ("R05 doesn't block this project, because...") keyed
  by project + rule_id, re-checked against every subsequent readiness
  call. `created_by_id` is required, not optional: an unattributed
  override isn't an audit trail, just an unexplained bypass.
- **New rules R07-R13**, one per previously-uncovered category:
  API specification present (completeness), manufacturer GMP status
  certified (completeness), an API's manufacturer actually has the
  API_MANUFACTURER role and not just any role (reference integrity — a
  FK alone only proves the referenced row *exists*, not that it's the
  *right kind* of row), residual solvents checked against a small
  hard-coded ICH Q3C limit table (regulatory limit, numbers only, never
  guideline prose — same copyright-safe principle as the P03 KB),
  a pharmacopoeial-citation reminder that fires as INFO on every
  compendial reference (never blocks — pharmacopoeia text itself is
  never stored here at all), pack size mentioned in packaging artwork
  (consistency), and R13 (above).
- **A genuinely clean dossier still has findings:** R11 fires an INFO
  reminder on every pharmacopoeia citation, which is normal and expected
  (BP/USP-NF citations are ordinary, not defects) — `assert findings ==
  []` from the old tests had to become `assert not [f for f in findings
  if f.severity != INFO]`. Exportability, not an empty report, is the
  real signal.
- **A real bug found by an existing, previously-unexercised test:**
  R05 crashed with `TypeError` on a product with no `shelf_life_months`
  set yet (a perfectly normal state right after creating a product via
  the API) -- surfaced by `test_readiness_placeholder` once it started
  exercising the real engine instead of the P02 stub. Fixed by returning
  early rather than comparing against `None`.
- **EXAMOX/LAMOX seed fixtures made genuinely complete**, not just their
  tests patched around new findings: added `specifications` to each API,
  `gmp_status=CERTIFIED` to each manufacturer, and an unexpired CPP
  certificate -- so "the corrected variant passes" stays a meaningful
  claim under the new rules, not something achieved by weakening the
  assertion.
- **Concept to revisit:** R10's residual-solvent parsing is a regex over
  free text ("Methanol: 3500 ppm") — deliberately WARNING, not ERROR,
  because a parsing miss or false-positive is a real risk with heuristic
  text extraction; a human reviews every warning regardless.

113 tests passing against a live Postgres (103 + 10 that self-skip
without one, same convention as every prior KB/narrative test).

---

## Interlude before P06 — combination products (Ampicillin+Cloxacillin fix)

A direct question ("does this support multi-API products like AMPICLOX or
artemether-lumefantrine?") surfaced a real gap: every product built through
P05 was implicitly single-API, and `Product.apis` being a list didn't
actually make combinations work.

- **Root cause: strength lived on `Product` (one value), not on
  `ActiveIngredient`.** A fixed-dose combination has one strength per
  active, not one for the product as a whole — there was nowhere to put
  a second value. Fixed by moving `strength_value`/`strength_unit` to
  `ActiveIngredient` (migration `bf6ef09c07bf`) and adding `Product.
  strength_display`, a plain Python `@property` (not a column) that joins
  every API's "name value unit" with " + " -- single- and multi-API
  products render through the exact same code path, no special case for
  N=1. Every template referencing the old `product.strength_value`/
  `strength_unit` pair (cover letter, 3.2.P.1, QOS, and the pre-P00
  Markdown prototype) was repointed at `strength_display`.
- **Two latent `apis[0]` bugs, both real, both fixed:** R01 (strength
  narrative-consistency) only ever checked the product's single declared
  strength, so a combination product's second active was invisible to it
  by construction. R04 (salt/base batch arithmetic) used `apis[0]`'s salt
  factor for every batch line regardless of which active it actually was.
  Fixed by adding `BatchFormulaLine.active_ingredient_id` (nullable FK) so
  a batch line can name which API it reconciles against, and rewriting
  both rules to loop over every API/line rather than assume there's
  exactly one.
- **New seed fixture, `app/seed/ampiclox.py`** (Ampicillin + Cloxacillin,
  a real NAFDAC-registered combination): its only planted defect is on
  Cloxacillin's narrative strength (125mg vs declared 250mg) specifically
  because that's a defect the OLD single-API-assuming R01 could never
  have caught — proof the rewrite actually works, not just that it
  doesn't crash. Both SMILES (ampicillin, cloxacillin) verified against
  RDKit's own molecular-formula calculation before trusting them, same
  habit as amoxicillin's in the prior interlude.
- **A real, previously-latent test flakiness risk, found and fixed along
  the way:** several sync-SQLite test fixtures used a plain `Session
  (engine)` (default `expire_on_commit=True`) and never re-touched
  relationship collections after `session.refresh()` (which only refreshes
  an object's own scalar columns, not relationships). Once
  `strength_display` started reading `self.apis` from outside the
  original fixture call, this occasionally surfaced as a
  `DetachedInstanceError` -- the underlying Session becoming eligible for
  garbage collection once the fixture function returned, with exactly
  when that happened depending on Python's cyclic GC timing rather than
  anything deterministic. Fixed by adding `expire_on_commit=False`
  everywhere this pattern appears, matching the async `pg_session_factory`
  fixture's own setting (see P05's build-log entry on why that flag
  matters) -- relationships populated via plain `.append()` before commit
  now just stay valid Python objects, no lazy-load ever required.
- **Concept to revisit:** this is a second real occurrence of "a rule that
  silently assumed N=1" (after the chemical-structure image's own
  `apis[0]` shortcut in the prior interlude, which is still there,
  unfixed, and now flagged consistently) -- worth deliberately scanning
  for this shape of bug (`apis[0]`, `.first()`, singular fields backing a
  1:N relationship) before treating any rule or renderer as "done."

5 new tests (AMPICLOX fixture + rule proofs); 87 passing overall.

---

## Interlude before P06 — Certificates, QOS, chemical structures

Not a numbered phase — a human-requested expansion, done before returning to
the P06 rule-engine plan, because it un-blocks a rule (certificate expiry)
that P06 would otherwise have had to scope out for lack of data.

- **`Certificate` model** (migration `76d6a4fb05a9`): `certificate_type`
  (CPP/GMP/CEP/CoA/free-sale), `issuing_authority`, `certificate_number`,
  `issue_date`, `expiry_date`, linked to a `Product` (required) and
  optionally a `Manufacturer` (for site-specific certs like GMP). All of
  issuing_authority/number/dates are nullable *on purpose* — a row can (and
  should) exist the moment a project is known to need a CPP, long before
  anyone has actually obtained one.
- **`app/templating/certificates.py`: placeholder generation, never
  fabricated content.** A certificate is proof issued by a third party (a
  regulator, EDQM, a lab) — the platform cannot write one without violating
  AGENTS.md §5's determinism boundary the same way narrative generation
  would if it invented a number. What it CAN do is emit a one-page,
  clearly-labeled ".docx" ("REPLACE THIS FILE WITH...") at the exact path
  the real certificate belongs at, so a missing certificate is a loud gap
  in the assembled package, not a silent one. Plain `python-docx`, not
  docxtpl — there's no template to fill, just a handful of values on a
  page. Storage key is scoped by **product**, not project (`products/
  {id}/certificates/{cert_id}.docx`) — a GMP certificate is a fact about a
  manufacturing site, reusable across whichever Projects file that same
  Product, same reasoning as Product itself being reusable master data.
- **Chemical structure rendering** (`app/templating/chemistry.py`, new
  dependency `rdkit`): `ActiveIngredient.smiles` (new nullable column) ->
  a 2D structure PNG via RDKit, the standard cheminformatics toolkit for
  this in pharma. Deliberately raises `InvalidSmilesError` on a SMILES that
  doesn't parse rather than silently producing nothing — a malformed
  SMILES is a data-entry error in a structured field, same category as a
  bad strength value, not a "not yet available" state.
- **`SectionSpec.structure_image_slot`** (`app/templating/registry.py`):
  any section can opt in to an embedded structure image by naming a
  context key here, matched by a `{{ key }}` placeholder in its template —
  not hard-coded to QOS. `render.py`'s `_build_structure_image` binds a
  docxtpl `InlineImage` when the product's (first) API has a `smiles`, or
  falls back to a plain-text placeholder (`"[[Structure not available...]]"`)
  when it doesn't — same bracket-placeholder convention as an unapproved
  narrative slot. Both a real `InlineImage` and a plain string can be bound
  to the same `{{ }}` tag; docxtpl just renders whichever type it's given.
- **QOS (`2.3`) registered as a normal fourth `SectionSpec`** — template,
  one narrative slot (`overview`), a `grounding_query`, and the new
  `structure_image_slot`. Went through the *exact* existing P04/P05
  pipeline with zero changes to `generate_narrative`, the guardrails, or
  the audit trail (see `test_generate_works_unchanged_for_the_new_qos_
  section` in test_narrative.py) — the registry-driven design's whole
  payoff, the same "open/closed" point made in the P04 checkpoint quiz.
- **Real SMILES on both seed fixtures** (EXAMOX and LAMOX): amoxicillin's
  actual structure, verified against RDKit's own molecular-formula
  calculation (C16H19N3O5S) before trusting it, same "verify before
  trusting real data" habit as P04's docxtpl row-loop fix.
- **Concept to revisit:** RDKit is a real dependency (~35MB wheel) — the
  right tool for correctness in a pharma context, but worth remembering
  as a deliberate tradeoff, not a free addition, next time dependency
  weight comes up.

12 new tests (chemistry, certificates, QOS rendering, QOS narrative
generation); 82 passing overall.

---

## P05 — AI Narrative Generation (LLM writes prose ONLY)

Fills the narrative slots P04 left as placeholders, with grounded/cited
prose and a full audit trail, per AGENTS.md §5's "everything the LLM
writes is reviewable." New pieces: `app/llm/client.py` (provider-abstracted
`LLMClient` — real + fake, same shape as P03's embedding client and P04's
storage client, now a fourth time), `app/narrative/` (facts.py, guardrails.py,
generate.py, review.py, context.py), a `NarrativeGeneration` audit-trail
model + migration, and `/projects/{id}/sections/{sec}/narrative/{slot}`
endpoints (`:generate`, `:approve`, `:edit`, plus a list GET).

- **LLM provider deviation from AGENTS.md §3's example:** the human chose
  Google Gemini over Anthropic Claude — a free tier generous enough for
  this project's volume, rather than requiring a paid key. `LLMClient` is
  provider-abstracted exactly as planned; only the concrete backend
  differs from the doc's example. AGENTS.md §3 updated to say so.
- **Guardrails have two different severities, matching the prompt's own
  wording:** numeric leakage (`check_numeric_leakage`) is a WARNING —
  flagged in the persisted row for human review, never blocking, because a
  number can leak in harmlessly (a count, not a regulatory figure) and
  that's a human judgment call. Fabricated citations
  (`check_citations`) are a hard BLOCK — `NarrativeGuardrailError` raised
  *before* anything is persisted — because the model was told exactly
  which sources it may cite, so citing anything else is unambiguous, not
  a judgment call.
- **The leakage whitelist is the rendered prompt text, not the ORM graph:**
  `app/narrative/facts.py` renders the same P04 `build_context()` dict
  (minus `narrative`) that's already going into the prompt, and the
  guardrail compares against *that* — not against "any number anywhere in
  the product's tables," which would let a coincidental match slip a real
  hallucination past the check. Bookkeeping columns (id/created_at/
  updated_at/`*_id` foreign keys) are excluded from the render — pure noise
  for both the prompt and the whitelist, and a UUID's stray digit runs
  would otherwise weaken the leakage check.
- **The audit trail's sources are a real many-to-many FK to `KBChunk`**
  (`narrative_generation_source`), not a JSON id list — same "let the
  database prove it" reasoning as the P03 checkpoint discussion: a FK row
  proves the chunk really exists and was really retrieved.
- **`final_text`, never `output`, is what P04's context builder reads**
  (`app/narrative/context.py`'s `get_approved_narrative`, wired in as a
  separate async step composed with `render_section`, not merged into
  P04's synchronous, DB-free `build_context`): a PENDING draft can only
  ever reach a rendered document through `approve_narrative`/
  `edit_narrative`, both of which require an explicit human action. There
  is no code path that promotes a draft to usable text on its own.
- **Concept to revisit:** the leakage guardrail is a blunt instrument — a
  legitimately-cited source excerpt can contain numbers (section numbers,
  dates) that aren't in the product facts and will trip a warning anyway.
  That's a real limitation of a regex-based check, deliberately not
  "fixed" by making it smarter here — warnings are for a human to judge,
  not for the code to adjudicate.

73 tests passing against a live Postgres (64 passing + 9 self-skipping
without one — P03's existing 2 plus 7 new P05 tests, same
`pg_session_factory` convention; CI's pgvector service always runs all
73).

---

## P04 — Section Template Engine (deterministic fill)

Converted the pre-P00 Markdown prototype (`app/templating/section_map.py`'s
`render_p1`) into a real docxtpl pipeline: a typed section registry
(`app/templating/registry.py`), a context builder
(`app/templating/context.py`), and a renderer
(`app/templating/render.py`) that fills a `.docx` template and uploads it
via a new object-storage abstraction (`app/core/storage.py`).

- **Scoped to 3 of the prompt's 6 listed sections:** cover letter (1.0),
  `3.2.P.1` (description & composition, with a `BatchFormulaLine`-driven
  table), and `3.2.P.8.1` (stability summary, table from `StabilityStudy`
  rows). `3.2.P.5.1` (finished-product specs) and `2.3` (QOS) need data
  (release-test limits, quality-overview narrative structure) that doesn't
  exist in the P01 model yet — adding it now would be scope creep into
  P01/P06. Same call as P03's "seed 2 real guidelines, not the whole ICH
  corpus." Registering a 4th section is "add one more `SectionSpec` entry
  + one `.docx` + one context branch," not a new pattern.
- **`section_map.py` untouched, not replaced:** its `render_p1` (Markdown
  output) still backs `test_rendered_section_cannot_contain_bugs` and
  `run_demo.py`, which test/demo the *rule engine* catching real LAMOX
  copy-paste bugs — a different concern from the template engine itself.
  The real registry lives in the new `registry.py` instead of overwriting
  that file.
- **Object storage gets the same provider-abstraction treatment as the LLM
  client (AGENTS.md §3) and P03's embedding client:** `StorageClient` ABC,
  `S3StorageClient` (boto3 against MinIO) and `InMemoryStorageClient`
  (dict-backed, the new `storage_provider=memory` dev/test default — no
  MinIO container needed to run the suite). Third time this exact shape
  (interface + config-selected implementation + cached getter) has been
  built in this repo.
- **Templates are real `.docx` files, generated programmatically** (via
  `python-docx`, since there's no Word GUI here) and checked into
  `backend/templates/`. Non-obvious docxtpl mechanic worth remembering:
  its `{%tr for x in y %}` / `{%tr endfor %}` row-loop tags each consume
  the *entire* table row they appear in (replacing it with the bare
  `{% for %}`/`{% endfor %}` Jinja tag) — so the tag needs its own
  dedicated marker row, separate from the data row with the real
  `{{ }}` placeholders, not combined into the same cell. Verified this
  by rendering with a synthetic 3-item list before trusting it against
  real data.
- **Tests** unzip the rendered `.docx` and check `word/document.xml`
  content directly (brand name, strength, composition/stability table
  values, narrative placeholder text) rather than just asserting
  `render()` didn't raise — proving substitution actually happened.
- **Concept to revisit:** `narrative` slots are always present in the
  context dict (defaulting to `None` per slot), even when no narrative is
  supplied — never simply absent — because an absent key would raise a
  Jinja `Undefined` error where the template expects `narrative.x or
  '[[placeholder]]'` to fall back gracefully.

42 tests passing (2 skipped, need real Postgres — same as P03).

---

## P03 — Regulatory Knowledge Base + RAG (copyright-safe)

Retrieval layer over pgvector: `KBDocument`/`KBChunk` models, a
provider-abstracted embedding client, a heading-aware chunker, an
allowlist-gated ingestion pipeline, a cosine-similarity retrieval service,
and `POST /kb/ingest` / `GET /kb/search` endpoints, in `app/knowledge/`
(this repo uses flat top-level dirs under `app/` for each concern —
`validation/`, `templating/`, now `knowledge/` — rather than the nested
`app/services/knowledge/` path in AGENTS.md §4's original plan; noting the
deviation here per AGENTS.md's own instruction).

- **Allowlist as types, not a runtime check:** `KBSource` and `KBLicense`
  (`app/models/enums.py`) *are* the allowlist AGENTS.md §5 requires —
  there's no enum member for USP/Ph. Eur./BP/JP, so `ingest_document`
  rejects a disallowed source/license before touching the database, the
  same "physically cannot store a bad value" philosophy as every other
  controlled vocabulary in this project. Tests: `test_ingest_rejects_
  disallowed_source`/`_license` in `test_knowledge.py`, plus an HTTP-level
  422 check in `test_kb_api.py`.
- **Two real seed documents, not placeholders:** fetched ICH Q1A(R2)
  (Stability Testing of New Drug Substances and Products, Step 4,
  2003-02-06) and M4Q(R1) (CTD for Registration of Pharmaceuticals: Quality,
  Step 4, 2002-09-12) from the official `database.ich.org`, verified with
  `pypdf` text extraction (not fabricated), checked into
  `reference/kb_sources/ich/`, and ingested via `scripts/seed_kb.py` — 88 +
  69 chunks in the live Postgres. ICH harmonised guidelines are adopted
  verbatim into national regulation by design, which is why AGENTS.md
  treats them (unlike pharmacopoeias) as freely redistributable.
- **Chunker is heading-aware, line-reflowed, not paragraph-split:**
  `app/knowledge/chunking.py` walks line-by-line rather than splitting on
  blank lines, because pypdf's extraction puts a newline per *visual* PDF
  line, not per paragraph — a blank-line split would miss headings that
  run straight into their body text and would leave mid-sentence line
  wraps in the output. **Known limitation:** the heading regex
  occasionally misfires on numbered list items (e.g. "3. If the submission
  does not include..." got tagged as a section label in the live Q1A(R2)
  ingest) — acceptable for a first-pass heuristic, revisit if citation
  precision matters more once P05/P10 consume this.
- **Embedding dimension is a hard-coded constant** (`EMBEDDING_DIMENSION =
  512` in `app/models/kb.py`), not read from `Settings`, because pgvector
  fixes a column's vector width at the schema level — switching
  `embedding_model` to one with a different output size needs a new
  migration, not an env change. 512 matches `voyage-3-lite`.
- **Offline-first embedding client:** `app/knowledge/embeddings.py` has a
  real `VoyageEmbeddingClient` and a `FakeEmbeddingClient` — a deterministic
  hashed-bag-of-words embedder (no network/key) used for local dev/tests via
  `EMBEDDING_PROVIDER=fake`. A real Voyage key is already in `.env` for
  whenever live embeddings are wanted; re-running `scripts/seed_kb.py` after
  flipping the provider re-embeds idempotently (replace, not duplicate).
- **CI gained a Postgres+pgvector service** (`pgvector/pgvector:pg16`) —
  the search round-trip test needs `KBChunk.embedding.cosine_distance(...)`,
  which compiles to pgvector's `<=>` operator and has no SQLite equivalent.
  Allowlist-rejection and re-ingest-idempotency tests still run on the
  existing SQLite fixture (pure relational logic, no vector ops). The
  Postgres-dependent tests self-skip if no Postgres is reachable, so
  `pytest -q` still passes without `docker compose up -d db` running
  locally.
- **HNSW over IVFFlat** for the `kb_chunk.embedding` index: IVFFlat needs a
  representative sample loaded before its clustering trains well, awkward
  for a KB seeded a few documents at a time; HNSW builds incrementally with
  good recall from the first row.
- **Incident, same shape as the P01 "downgrade drops real data" lesson:**
  an early version of the throwaway-Postgres test fixture used
  `str(sqlalchemy_url)` to build the connection string for the async
  engine — `URL.__str__` masks the password as `***` for logging safety,
  which broke the connection with an opaque "password authentication
  failed" error even though the maintenance connection (built from
  `render_as_string(hide_password=False)`) worked fine right next to it.
  Fixed by passing the `URL` object directly to `create_async_engine`
  instead of stringifying it. **Lesson:** never call `str()` on a
  SQLAlchemy URL when the string will actually be used to connect —
  `str()`/`repr()` on credentialed objects should be assumed lossy by
  default.
- **Tests:** 39 passing (35 existing + 4 new: two allowlist-rejection unit
  tests, one idempotent-re-ingest unit test on SQLite, one full search
  round-trip on real Postgres) plus 4 HTTP-level tests in `test_kb_api.py`
  (auth-required, ingest success, allowlist-rejection-via-API,
  full-stack search). All 39 pass together; ruff and black clean on every
  file this phase touched.
- **Verified against live Postgres + containerized API:** ran
  `scripts/seed_kb.py` against the docker-compose `db`, confirmed 88+69
  chunks landed; rebuilt and started the `api` container, hit
  `GET /kb/search?q=...` over real HTTP and got correctly ranked, cited
  ICH chunks back.

**Next:** P04 (template engine — turn 3.2.P.1 into a real docxtpl .docx;
P03's retrieval service becomes available to P05's narrative generator
once that phase exists).

## P02 — Backend API skeleton (CRUD, auth, project/sequence)

FastAPI routers over every P01 entity, JWT auth, and the sequence/readiness
endpoints, in `app/api/`.

- **Routers:** `products.py` (top-level CRUD — Product is master data, not
  owned by a Project). Its six children (manufacturers, APIs, excipients,
  packaging, stability, clinical) are nested under
  `/products/{product_id}/...` since none make sense detached from a product;
  they're generated by one factory (`product_children.py` builds the
  identical CRUD shape per resource, instantiated in `nested.py`) rather than
  six near-duplicate files. `projects.py` covers Project CRUD plus the two
  P02-specific endpoints: `POST /projects/{id}/sequences` (auto-numbers
  `0000`, `0001`, ... from `max(existing) + 1`, via a request schema with no
  `number` field so the client physically cannot supply one) and
  `GET /projects/{id}/readiness` (placeholder `{ready: false, checks: []}`
  until P06).
- **Auth:** `users` table (email + argon2 hash via `argon2-cffi`), JWT bearer
  tokens (`pyjwt`), `POST /auth/register` + `POST /auth/login`
  (`OAuth2PasswordRequestForm`, so `/docs`' built-in "Authorize" button works
  out of the box). Every mutating endpoint depends on `get_current_user`;
  reads stay open. No roles, no OAuth providers — matches the phase's
  "don't gold-plate" instruction.
- **Errors:** one envelope, `{"error": {"code", "message"}}`, via two
  exception handlers in `app/api/errors.py` (`HTTPException` and
  `RequestValidationError`) so 404/401/409/422 all come back the same shape
  regardless of which router raised them.
- **Async relationship loading (the real gotcha of this phase):** SQLAlchemy
  async cannot lazy-load a relationship outside the query that fetched it —
  touching an un-loaded collection from a `*Read` schema raises
  `MissingGreenlet`. Two traps found by the tests, not by inspection: (1)
  `Session.refresh()` expires relationship attributes without reloading
  them, so `create_product` switched to re-fetching via the same
  `selectinload`-equipped query used by `GET`, instead of trusting
  `refresh()`; (2) all eager-load options are centralized in
  `app/api/loading.py` (`PRODUCT_CHILD_OPTIONS`, `PROJECT_CHILD_OPTIONS`) so
  every router loads exactly the shape its `Read` schema nests.
- **Generic-router typing trap:** `product_children.py`'s factory takes
  `create_schema`/`update_schema` as parameters and uses them as a nested
  function's parameter annotation. With `from __future__ import annotations`
  (postponed evaluation), FastAPI can't resolve that annotation — it's a
  string referring to a closure variable, not a module global — and schema
  generation fails with `PydanticUserError` at `/openapi.json` request time,
  not at import time. Fixed by removing the future-import from that one
  file so the annotations bind to the real class objects eagerly.
- **Tests:** 31 passing (17 new: `test_auth_api.py`, `test_products_api.py`,
  `test_projects_api.py`), via `tests/conftest.py` — an in-memory
  `sqlite+aiosqlite` engine pinned to a single connection (`StaticPool`,
  since in-memory SQLite is otherwise a fresh empty DB per pool checkout),
  wired into the real app through `dependency_overrides[get_db]`.
- **New dependencies:** `pyjwt`, `argon2-cffi`, `email-validator` (pydantic's
  `EmailStr`), `python-multipart` (`OAuth2PasswordRequestForm` needs form
  parsing).
- **Verified against live Postgres:** rebuilt the `api` container, hit
  `/health`, `/docs`, and `/openapi.json` (24 paths), then ran a full
  register → login → create product → create project → auto-numbered
  sequences → readiness → unauthenticated-write-rejected flow over real
  HTTP against the docker-compose stack; cleaned up the smoke-test rows
  afterward so the live DB still holds only the seeded EXAMOX product.

**Next:** P03 (Regulatory Knowledge Base + RAG).

## Seed rebrand — EXAMOX replaces Parazon (2026-07-12)

The P01 demo seed (`scripts/seed_demo.py`) previously loaded a third-party
placeholder ("Parazon"/paracetamol). Replaced it with our own company's real
product so the live database reflects EXAGON data: `app/seed/examox.py`
builds EXAMOX (Amoxicillin 500 mg hard gelatin capsules, manufacturer Exagon,
Gwagwalada, Abuja, NAFDAC renewal) — structured identically to
`app/seed/lamox.py` (buggy vs. corrected 3.2.P.1 narrative pair), only the
branding/company details changed. The buggy variant keeps the same three
defect classes (wrong strength "250mg", wrong dosage-form word "Tablets", a
leftover foreign-product reference) so R01–R03 still have fixture material to
catch; the foreign brand used for the R03 test is invented ("NUFLOX", added
to the `known_brands` registry in `app/validation/rules.py`) rather than
reusing LATRIM, so it's clearly our own test data and not confused with the
real LAMOX dossier. Unlike Parazon, EXAMOX's declared shelf life (24 months)
equals its stability data (24 months) — no artificial R05 mismatch.
`scripts/seed_demo.py` is now idempotent: it looks up the "EXAMOX renewal"
project by name before inserting and skips if already seeded. Ran against the
live Postgres (after removing the old Parazon rows); confirmed via query.
Tests updated (`test_seed_demo.py`) to match; 14 passing.

## P01 — Data model (SQLAlchemy + Alembic + Pydantic)

All nine AGENTS.md §6 entities as SQLAlchemy models in `app/models/`, plus
two supporting entities the earlier vertical slice already established
(`BatchFormulaLine` for the 3.2.P.1 composition table, `Section` for
rendered narrative text). UUID PKs + `created_at`/`updated_at` from a shared
`Base`. Enums centralized in `app/models/enums.py`, backed by native Postgres
`ENUM` types via Alembic. Pydantic `Create`/`Update`/`Read` schemas in
`app/schemas/` for every entity; `ProductRead`/`ProjectRead` nest children
for full-document serialization.

- **Migration:** `b0a8331ddd02_p01_full_data_model` generated and applied
  cleanly to the live docker-compose Postgres — verified via `\dt` (12
  tables) and `alembic_version`. Fixed a latent cross-dialect bug in its
  `downgrade()`: the Postgres `DROP TYPE` cleanup loop isn't valid SQL on
  SQLite, so it's now gated on `dialect.name == "postgresql"` — needed so
  the migration-applies test can run against a throwaway SQLite file in CI
  (no Postgres service defined there) instead of a live database.
- **Seed:** `scripts/seed_demo.py` — a generic demo product ("Parazon",
  paracetamol 500mg tablet), distinct from `app/seed/lamox.py`. Deliberately
  declares a 36-month shelf life while the longest long-term stability study
  on file only supports 24 months — the fixture P06's shelf-life-vs-stability
  rule will check. Ran against the live Postgres; confirmed via query.
- **Tests:** 11 passing. Added `test_migration.py` (upgrade creates all
  tables / downgrade removes them, against a throwaway SQLite file) and
  `test_seed_demo.py` (full project populates; shelf-life mismatch is real).
- **Lint fix:** every model file used forward-reference strings
  (`Mapped["Product"]`) for relationships without importing the referenced
  class — works at runtime because SQLAlchemy resolves these lazily via its
  mapper registry, but `ruff` flagged all of them as undefined names (F821).
  Fixed with standard `TYPE_CHECKING`-guarded imports across all nine files.
- **Incident during build:** an early version of the migration-applies test
  didn't realize `alembic/env.py` unconditionally rebuilds `sqlalchemy.url`
  from `Settings`/`.env`, ignoring whatever URL the test's `Config` object
  set. Its downgrade half ran for real against the live dev Postgres and
  dropped every table. No data lost beyond that dev database's seed/migration
  output, both trivially reprovisioned; the test was rewritten to monkeypatch
  `DATABASE_URL` + clear the `get_settings()` cache before invoking alembic,
  with an explicit assertion guarding against ever hitting a real DB again.
  **Lesson:** when a test's DB config might get silently overridden by
  app-level settings plumbing, verify the actual resolved connection target
  before running anything destructive against it.

**Next:** P02 (backend API skeleton — CRUD, auth, project/sequence).

## P00 — Repo scaffold, docker-compose, tooling

Verified working: `docker compose up -d` brings up `db` (healthy, Postgres +
pgvector), `minio` (healthy), and `api`; `curl http://localhost:8000/health`
returns `{"status":"ok","version":"0.1.0"}`; tests pass (7, `pytest -q`).

- **Decision:** chose `uv` for Python dependency management (over
  pip/poetry) — fast installs, single lockfile (`uv.lock`), good fit for the
  devcontainer/Docker build layers.
- **Note:** the stack runs in GitHub Codespaces via the devcontainer, so the
  full docker-compose environment (db, minio, api) is available without any
  local setup.

**Next:** P01 (data model — SQLAlchemy + Alembic + Pydantic), building on the
LAMOX vertical-slice models already in place below.

## Vertical slice (P01 / P04 / P06 — partial) — starting point

A runnable slice built from the real LAMOX dossier, before the full P00 scaffold.

- **P01:** SQLAlchemy 2.x models in `app/models/` — Product, ActiveIngredient
  (with base strength + `salt_factor` split), Excipient, Packaging,
  StabilityStudy, ClinicalEntry, BatchFormulaLine, Section, Project. Runs on
  SQLite for now; same code will point at Postgres after P00.
- **P04:** `app/templating/section_map.py` renders 3.2.P.1 from structured data
  (data slots + a narrative slot). Not yet a docxtpl .docx — that's the next
  step.
- **P06:** `app/validation/` engine + rules R01–R06. R01–R03 catch the three
  real LAMOX copy-paste bugs (250 mg vs 500 mg; "Tablets" on a capsule; leftover
  "LATRIM" reference). R04 confirms the salt/base batch arithmetic. Export is
  gated on zero ERROR findings.
- **Tests:** 6 passing (`pytest -q`).
- **Decision:** stored strength as base + salt_factor rather than a single
  string, so batch-quantity arithmetic is checkable.
- **Note/typo caught during build:** a test asserted `"250" not in output`,
  which wrongly tripped on the batch size `250000`; fixed to assert `"250 mg"`.
  Lesson: assert the meaning, not a substring.

**Next:** P00 (docker-compose + Postgres + FastAPI scaffold), then convert
3.2.P.1 to a real docxtpl .docx (P04), then wire validation behind an API (P02).
