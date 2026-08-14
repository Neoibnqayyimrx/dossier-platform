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
