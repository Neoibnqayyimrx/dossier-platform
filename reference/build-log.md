# Build Log

Append a short entry as each phase is completed: what was built, key decisions,
and one concept to revisit. Newest at the top.

---

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
