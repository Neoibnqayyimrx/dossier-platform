# AGENTS.md — Regulatory Dossier Platform

> This is the master context file for the project. **Every prompt in `/prompts` refers back to this file.**
> When you (Claude Code) start any task, read this file first, then read the specific phase prompt.
> Keep this file updated: when a phase is completed, tick its box in the "Build Status" section and note any deviations.

---

## 1. What we are building

A **Regulatory Intelligence Platform** that turns structured product data into submission-ready pharmaceutical registration dossiers. It is **not** an "AI writes the dossier" tool. The AI writes *only* the narrative prose; everything structural, numerical, and regulatory is **deterministic**.

The guiding architecture:

```
USER
  → Product Information Wizard        (structured input, not documents)
  → Validation & Regulatory Rules     (deterministic)
  → Regulatory Knowledge Base (RAG)   (retrieval over guidelines)
  → AI Document Generation Engine     (narrative text ONLY)
  → Document Assembly Engine          (templates + data)
  → CTD / eCTD Folder + TOC Builder   (deterministic)
  → Quality Checker (Validation)      (deterministic + AI reviewer)
  → Final Submission Package
```

**Core principle, repeated because it matters:** the LLM fills narrative blocks only. Section numbering, folder structure, TOC, checksums, XML backbone, cross-field consistency — all deterministic code. If you find yourself asking the LLM to produce a folder tree, a checksum, or a table of numbers, stop and write code instead.

## 2. Target outputs, in build priority order

1. **NAFDAC / NAPAMS CTD package** (MVP). Nigeria's NAFDAC uses the NAPAMS portal (registration.nafdac.gov.ng) and expects a **CTD** dossier — structured folders + PDFs + a table of contents, uploaded to the portal. There is **no XML backbone requirement**. This is the realistic first deliverable and the least brittle. Build this first.
2. **eCTD v3.2.2 package** (FDA / EMA — "hard mode"). Adds the XML backbone (`index.xml`), regional backbone, `index-md5.txt`, per-leaf MD5 checksums, sequence numbering, and lifecycle operation attributes. See `/reference/ectd-backbone-architecture.md`. Build this as a **separable module** that consumes the same assembled documents as the CTD builder.
3. **eCTD v4.0 (HL7 RPS)** (future / optional). UUID-based "context of use" model. Do not build until 1 and 2 are solid.

See `/reference/nafdac-vs-fda-ema-scope.md` for the regulatory scoping detail.

## 3. Technology stack (agreed)

- **Frontend:** Next.js (React), TypeScript, Tailwind.
- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic.
- **Database:** PostgreSQL 16 + `pgvector` extension (single DB for relational data AND vector store — do not add a separate vector DB unless we outgrow pgvector).
- **Object storage:** S3-compatible. Use **MinIO** locally via docker-compose; production can swap to real S3.
- **Document generation:** `docxtpl` (templated DOCX from Jinja2-style templates), `python-docx` (fine control), **LibreOffice headless** for DOCX→PDF, `PyMuPDF` (fitz) + `pypdf` for PDF merge/bookmarks/manipulation.
- **XML backbone:** `lxml` (never string-concatenate XML).
- **AI orchestration:** plain Python service layer first; only introduce LangGraph/n8n if a workflow genuinely needs multi-step branching. Do not add orchestration frameworks prematurely.
- **LLM:** provider-abstracted. A single `LLMClient` interface with a config-selected backend (Anthropic Claude or other). Model name lives in config/env, never hard-coded in business logic.
- **Testing:** `pytest`, `pytest-asyncio`, `httpx` for API tests. Frontend: Vitest + Playwright for the wizard flow.
- **Containerization:** Docker + docker-compose for local dev (api, db, minio, libreoffice worker if separated).

## 4. Repository layout (monorepo)

```
dossier-platform/
├── AGENTS.md                    # this file, copied into the repo root
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                # config, db session, security
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── api/                 # FastAPI routers
│   │   ├── services/
│   │   │   ├── knowledge/       # RAG: ingestion, retrieval
│   │   │   ├── templating/      # docxtpl template fill
│   │   │   ├── narrative/       # LLM narrative generation
│   │   │   ├── validation/      # deterministic rule engine
│   │   │   ├── assembly/        # DOCX→PDF, bookmarks, granular leaves
│   │   │   ├── ctd/             # NAFDAC/NAPAMS CTD folder builder
│   │   │   └── ectd/            # eCTD v3.2.2 XML backbone builder
│   │   └── llm/                 # provider-abstracted LLM client
│   ├── templates/               # docxtpl section templates
│   ├── alembic/
│   └── tests/
├── frontend/
│   └── (Next.js app)
└── reference/                   # regulatory reference docs (copied from this kit)
```

## 5. Cross-cutting rules (apply to every phase)

- **Determinism boundary.** Any value that a regulator cross-checks (strength, shelf life, batch numbers, section numbers, checksums, dates) is produced by code from the data model — never by the LLM. The LLM only writes prose inside clearly delimited `<<AI WRITES ONLY THIS>>` template blocks.
- **Everything the LLM writes is reviewable.** Store the prompt, the model, the retrieved context, and the output for every narrative generation, so a human (and an audit) can trace it.
- **No copyrighted corpora in the knowledge base.** ICH guidelines and most agency guidance are freely redistributable. **Pharmacopoeias (USP, Ph. Eur., BP) are copyrighted — do NOT ingest their monographs.** The KB stores references/citations to them, not their text. This is a hard rule; see Phase 03.
- **Idempotent builders.** Running the CTD/eCTD builder twice on the same data produces byte-identical output (except where a real new sequence is intended). Checksums depend on this.
- **Validation is a gate, not a suggestion.** The package cannot be exported until deterministic validation passes (or a human explicitly overrides with a logged reason).
- **Test-first for the deterministic core.** Rule engine, checksum, XML backbone, and TOC builder must have unit tests with known-good fixtures before they're wired into the API.
- **Config over hard-coding.** Region profiles (NAFDAC, FDA, EMA), model names, storage endpoints, and paths all live in config.
- **Small commits, one concern each.** Reference the phase number in commit messages, e.g. `[P06] add shelf-life vs stability consistency rule`.

## 6. Data model (canonical entities)

These entities are the single source of truth. Templates and builders read from here; the LLM never invents them.

- **Product** — brand name, generic name, strength, dosage form, ATC code, shelf life, storage condition, pack size, route of administration, legal status, country, registration type (new/renewal/variation).
- **Manufacturer** — name, site address, GMP status, country, WHO-GMP / PIC-S flags, manufacturing licence.
- **API (active ingredient)** — name, DMF number, CEP, manufacturer, retest period, specifications, particle size, residual solvents.
- **Excipient** — name, function, grade, supplier, compendial status.
- **Packaging** — primary, secondary, artwork, label, leaflet, carton.
- **Stability** — accelerated, long-term, intermediate, protocol, summary.
- **Clinical** — bioequivalence, literature, reference product, clinical studies.
- **Project / Application** — ties a Product to a target region profile and a set of Sequences.
- **Sequence** — one regulatory transaction (`0000`, `0001`…); only meaningful for eCTD, but modeled from the start.

Full field definitions and relationships are specified in Phase 01.

## 7. Build status (update as you go)

- [x] P00 — Repo scaffold, docker-compose, tooling, CI
- [x] P01 — Data model (SQLAlchemy + Alembic + Pydantic)
- [x] P02 — Backend API skeleton (CRUD, auth, project/sequence)
- [ ] P03 — Regulatory Knowledge Base + RAG (copyright-safe ingestion)
- [ ] P04 — Template engine (docxtpl section templates)
- [ ] P05 — AI narrative generation service (LLM, guardrailed)
- [ ] P06 — Deterministic validation / rule engine
- [ ] P07 — Document assembly + PDF (DOCX→PDF, bookmarks, granular leaves)
- [ ] P08 — CTD / NAPAMS folder + TOC builder (MVP output)
- [ ] P09 — eCTD v3.2.2 XML backbone builder
- [ ] P10 — eCTD validation (business rules + validator integration)
- [ ] P11 — Frontend wizard + dashboard + validation viewer
- [ ] P12 — eCTD v4.0 (RPS) — future

## 8. How to work through the prompts

Each file in `/prompts` is a self-contained task. Do them in order. At the start of each, re-read this AGENTS.md and the relevant `/reference` docs. At the end of each, update the Build Status checkboxes here and write a short note in `/reference/build-log.md` (create it in P00) describing what was built and any decisions or deviations. Do not skip ahead — later phases assume earlier ones exist.

## 9. LEARNING MODE (mandatory — the human is learning while we build)

**This project is being built to teach.** The human is an industrial pharmacist and software engineer who wants to understand the code, the language, the logic, AND the regulatory domain as we go — not just watch code appear. Treat every phase as a lesson, not just a task. Read `LEARNING.md` for the full protocol; the essentials:

- **Teach before you type.** Before writing code for a phase, explain in plain language *what* you're about to build, *why* it's structured that way, and what the key decisions/tradeoffs are. Get a "go" before generating large amounts of code.
- **Narrate as you build.** When you use a non-obvious language feature, library idiom, or design pattern, name it and explain it in one or two sentences. Assume strong pharma knowledge but don't assume familiarity with, e.g., async Python, ORM session lifecycles, pgvector, DTD validation, or React hooks.
- **Leave `WHY:` comments** on any code whose reasoning isn't obvious from reading it — especially in the rule engine, checksum/XML backbone, and lifecycle logic.
- **Connect code to regulation.** Whenever a piece of code exists *because a regulator requires it* (checksums, lifecycle operations, granularity, Module 1 contents), say so and point to `/reference/dossier-anatomy.md` or the backbone reference. The human wants to learn the dossier as much as the software.
- **Checkpoint and quiz.** At the end of each phase, write a short "What you learned" recap (3–5 bullets, split into *software* and *regulatory*), then pose 2–3 comprehension questions or one small hands-on exercise for the human to do themselves. Wait for them before moving on if they engage.
- **Let the human write some of it.** Periodically, instead of writing a function yourself, describe it and invite the human to implement it, then review their version. Good candidates: a single validation rule (P06), one docxtpl template (P04), one API endpoint (P02).
- **Pace over speed.** It is better to build one well-understood module than three opaque ones. Never dump an entire phase as one giant unexplained code block.

If the human ever says "just build it" for a specific part, respect that and move faster there — but default to teaching.
