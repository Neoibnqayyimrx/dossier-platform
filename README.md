# Dossier Platform

**Regulatory dossier automation for pharmaceutical products** — a FastAPI/PostgreSQL platform that models CTD/eCTD dossiers as structured data, renders submission sections from that data, and validates the whole dossier with a deterministic rule engine before anything is exported.

Built by a licensed pharmacist and software engineer: the data model and validation rules are grounded in real regulatory documentation work (NAFDAC-CTD first, with FDA/EMA scope mapped in `reference/`).

## The problem

Regulatory dossiers are assembled by copy-pasting between Word documents. The same fact — strength, dosage form, manufacturer — is restated dozens of times across Modules 1–5, and every restatement is a chance for the versions to drift apart. Regulators find these inconsistencies; companies eat the review-cycle delay.

## The approach

**Single source of truth, deterministic checks.** Every fact a regulator cross-checks lives once in a structured data model. Sections are *rendered* from the data, never hand-edited. A rule engine validates the aggregate before export — and it is deterministic code, not an LLM. (An LLM-assisted reviewer is on the roadmap strictly as an advisory layer for narrative prose; it never replaces the deterministic checks.)

## See it work (2 minutes)

```bash
cd backend
uv sync                     # curl -LsSf https://astral.sh/uv/install.sh | sh if you don't have uv
uv run python run_demo.py   # seeds LAMOX, validates it, renders section 3.2.P.1
uv run pytest -q            # test suite
```

The demo seeds a real product dossier (LAMOX, Amoxicillin 500 mg capsules) containing three genuine copy-paste bugs of the kind that reach regulators — a wrong strength, a wrong dosage form, and a leftover reference to a different product. The rule engine catches all three, blocks export, then shows a clean pass on the corrected data. That is the platform's value proposition, demonstrated on real content.

## Run the full stack

```bash
cp .env.example .env
docker compose up -d --build   # Postgres + pgvector, MinIO, API
curl http://localhost:8000/health
docker compose down
```

## Architecture

```
backend/app/
  core/          Settings (pydantic-settings), async SQLAlchemy engine/session
  models/        SQLAlchemy 2.x data model: product, active ingredient, excipients,
                 batch formula, packaging, stability, clinical, sequence, users
  schemas/       Pydantic v2 request/response schemas
  api/routers/   FastAPI routers: auth (JWT + argon2), projects, products,
                 nested child resources
  templating/    renders CTD sections (e.g. 3.2.P.1) from structured data;
                 docxtpl-based .docx output in progress
  validation/    deterministic rule engine — decorator-registered rules,
                 ERROR/WARNING/INFO severities, export gate on unresolved errors
  seed/          real worked-example seed data (buggy + corrected variants)
tests/           pytest suite
alembic/         async-ready migrations
.github/workflows/ci.yml   ruff + black + pytest on every push and PR
```

**Design decisions worth noting**

- **Rules as a registry.** Each validation rule is a small, independently testable function registered via a decorator. Rules will grow into the hundreds; the registry keeps them decoupled, and every finding names the offending values — never just "inconsistent."
- **Severity model with an export gate.** `ERROR` blocks export, `WARNING` is surfaced but allowed, `INFO` is informational — mirroring how regulatory reviewers actually triage findings.
- **Region rules live in config,** not scattered through code, because regulatory formats change and must be re-confirmed against the agency's current requirements (NAFDAC NAPAMS; FDA eCTD; EMA eSubmission) before any real submission.
- **Same models, two databases.** The demo and tests run on SQLite for speed; the docker-compose stack runs the identical models on Postgres — only the connection string changes.

## Stack

Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2.x (async) · Alembic · PostgreSQL + pgvector · MinIO · Docker Compose · docxtpl/python-docx · pytest · ruff · black · GitHub Actions CI · uv

## Coverage against a real dossier

**23/98 leaves** of a filed NAFDAC multisource dossier (Me Cure, Amlodipine
Tablets 5 mg) are produced from data today — including the fourteen sections
the dossier declares *not applicable*, which are filed as generated
statements citing the guideline that excuses them, not omitted. A further
**22 leaves accept an uploaded document** (a regulator's CPP, a CRO's study
report — paper no software can author), and the build refuses to export while
any of them is still a placeholder.

Two kinds of coverage, kept apart on purpose: run the check with no arguments
for what the *platform* can do, and with `--project <id>` for what one
*filing* actually has in. A route to attach a CPP is not the same fact as the
CPP being attached. The target is data, not prose —
`docs/target-toc.yaml` declares every leaf that dossier owes and how it is
produced; `uv run python -m scripts.check_target_toc` (run in CI on every push)
compares it against what the platform can actually render, and prints the gap
broken down by module, by production type, and by the foundation capability
blocking each leaf. The largest single blocker is the upload path: 22 leaves
are third-party artifacts the platform can only place, not author.

## Roadmap

- Grow the rule set and wire validation behind a `/readiness` API endpoint
- Full `docxtpl` .docx rendering of CTD sections
- eCTD v3.2.2 XML backbone generation (spec documented in `reference/`)
- Advisory-only LLM reviewer for narrative sections
- Frontend (React + TanStack)

## Repo guide

Domain background lives in `reference/` — a guided tour of CTD Modules 1–5, a NAFDAC vs FDA/EMA scope comparison, the eCTD backbone architecture, rules, and templates. `AGENTS.md` holds the build plan and phase breakdown.

---

**A caution worth keeping:** regulatory formats change. Before relying on any regulator-specific output for a real submission, confirm the current requirement on the agency's own site.
