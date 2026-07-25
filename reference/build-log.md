# Build Log

Append a short entry as each phase is completed: what was built, key decisions,
and one concept to revisit. Newest at the top.

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
