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

**98/98 leaves** of a filed NAFDAC multisource dossier (Me Cure, Amlodipine
Tablets 5 mg) now have a route to production, and CI fails the build if one
ever does not. That number means *every leaf has somewhere to come from* —
76 the platform renders from data, 22 it accepts as an uploaded file and
refuses to export without. It is deliberately **not** a claim that a
particular dossier is finished; that is the other question, and it is asked
per filing with `--project <id>`.

Those leaves include the fourteen sections the dossier declares *not
applicable*, which are filed as generated statements citing the guideline
that excuses them, not omitted. Sections that
repeat do so along whichever axis they belong to: a combination product owes
one 3.2.S per active, a three-pack product one 3.2.P.7 per pack, one 3.2.P.4.1
per excipient, each in its own folder named after its subject rather than an
index.

The specification is one table with three owners — the drug substance
(3.2.S.4.1), each excipient (3.2.P.4.1) and the finished product (3.2.P.5.1) —
so the batch analyses in 3.2.S.4.4 and 3.2.P.5.4 are checked against *the*
limit rather than against a copy of it: a result outside its own acceptance
criterion blocks the export and names the batch, the test, the result and the
limit. Stability is the same idea across time — a shelf life is checked
against the longest timepoint at which every test still met its criterion,
and 3.2.P.8.1 prints that figure rather than repeating the claim.

The bioequivalence study is data too, and it is where the single-source
premise is easiest to see. Leaf **1.4.1**, the Bioequivalence Trial
Information form, is a *Module 1* document generated with no prose at all out
of *Module 5* numbers; **5.2**'s tabular listing is walked from the studies
actually filed, so it cannot name one that is not there. A 90 % confidence
interval outside the acceptance window blocks the export and names the
parameter and the bound — and that window lives in the region profile
alongside the Module 1 slots, because it is a regulatory parameter that
changes, not a constant. A further
**22 leaves accept an uploaded document** (a regulator's CPP, a CRO's study
report — paper no software can author), and the build refuses to export while
any of them is still a placeholder.

The Summary of Product Characteristics (**1.3.1**), the outer and inner labels
(**1.3.2**) and the patient information leaflet (**1.3.3**) are rendered from
one dataset. These three contradict each other constantly in real filings —
a shelf-life extension updates two of the three — and the platform's answer is
not to check them but to leave nothing to check: strength, shelf life, storage,
pack size and the ingredient list are computed once, from the product, its
packaging rows and its stability data, and all three documents read that one
computation. The API *refuses* a write naming a derived field rather than
silently dropping it, and the wizard shows each one read-only beside a sentence
saying where it comes from. What can still genuinely diverge is checked: an
excipient in the batch formula but not in the leaflet blocks the export, and so
does a label permitting storage at 30 °C over a study that ran at 25 °C. The
leaflet's drafted prose is judged in a *patient* register — a different system
prompt and a different output check from the SmPC's, because "contraindicated
in hepatic impairment" is correct in one document and a failure in the other.

The three documents that are *derived from other documents* — the per-module
tables of contents (**1.1**, **2.1**, **3.1**, **5.1**), the Quality
Information Summary (**1.4.2**) and the Quality Overall Summary (**2.3**) —
hold no data of their own at all. A TOC is built from the files actually
placed in the package, so it cannot list a document that is not there or omit
one that is. The QIS and the QOS read the very context dicts their Module 3
sections render from: the QIS is NAFDAC's form layout and the QOS is ICH
M4Q's fourteen subsections, and neither is ever handed a model to re-query.
The consequence is worth stating plainly, because it is the defect the whole
platform exists to remove — a QOS that disagrees with Module 3 is the most
commonly raised quality deficiency there is, and it is never a decision, only
a second copy of a number updated once. Here 2.3.P.8 *is* 3.2.P.8.1's
sentence, so an unsupported shelf life is unprintable in the summary rather
than merely blocked at export.

Two kinds of coverage, kept apart on purpose: run the check with no arguments
for what the *platform* can do, and with `--project <id>` for what one
*filing* actually has in. A route to attach a CPP is not the same fact as the
CPP being attached, and a leaf a filing has scoped out (no biowaiver claimed,
no previous marketing authorization) is an answer rather than a hole. The
target is data, not prose — `docs/target-toc.yaml` declares every leaf that
dossier owes and how it is produced; `uv run python -m scripts.check_target_toc
--strict` runs in CI on every push and **fails the build** if an applicable
leaf has no route to production. The largest single dependency is the upload
path: 22 leaves are third-party artifacts the platform can only place, not
author.

The whole of it is proved end to end on a worked example. `app/seed/
amlodipine.py` seeds a complete, defect-free amlodipine 5 mg filing — the
product the target was derived from — and `tests/test_worked_example.py`
builds it: **102 leaf PDFs covering 93 target leaves**, with the other five
scoped out by the filer's own conditional answers, a table of contents per
module, and an eCTD backbone that validates against
`reference/ectd_dtd/ich-ectd-3-2.dtd`. 102 rather than 98 because a leaf
number is not a document count: 3.2.P.4.1 repeats per excipient, 3.2.P.3.1
per manufacturing site, 3.2.P.7 per pack, and three leaves file a generated
document beside an uploaded one.

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
