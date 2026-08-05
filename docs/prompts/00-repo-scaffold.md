# P00 — Repository Scaffold, Tooling, and Local Environment

**Before starting:** read `AGENTS.md` (sections 3, 4, 5) and both files in `/reference`.

## Goal

Stand up the monorepo skeleton, local dev environment (Postgres+pgvector, MinIO), and tooling so every later phase has a home. No business logic yet.

## Tasks

1. Create the monorepo layout exactly as in `AGENTS.md` §4 (`backend/`, `frontend/` placeholder, `reference/`). Copy `AGENTS.md` to the repo root and copy the `/reference` docs into `reference/`.
2. **Backend baseline:**
   - Python 3.11+, `pyproject.toml` (use `uv` or `poetry` — pick one, note it in the build log). Dependencies: `fastapi`, `uvicorn`, `pydantic>=2`, `pydantic-settings`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `pgvector`, `python-docx`, `docxtpl`, `pymupdf`, `pypdf`, `lxml`, `httpx`, `pytest`, `pytest-asyncio`.
   - `app/core/config.py` — `Settings` via `pydantic-settings`, reading from env: DB URL, MinIO endpoint/keys, LLM provider + model name, storage bucket. Nothing secret hard-coded.
   - `app/core/db.py` — async SQLAlchemy engine + session dependency.
   - `app/main.py` — FastAPI app with a `/health` endpoint returning `{status, version}`.
3. **docker-compose.yml** with services: `db` (postgres:16 with pgvector — use the `pgvector/pgvector:pg16` image), `minio`, and `api` (builds `backend/`). Include a one-shot init that enables the `vector` extension. Add named volumes.
4. **.env.example** documenting every variable `Settings` reads. Add a real `.env` to `.gitignore`.
5. **Alembic** initialized against the async engine (no migrations yet — that's P01).
6. **CI** (GitHub Actions): a workflow that installs deps, runs `ruff`/`black --check`, and runs `pytest`. Add `ruff` + `black` config.
7. **`reference/build-log.md`** — create it. Add the first entry: what tooling you chose (uv vs poetry) and why.
8. A smoke test: `pytest` proves `/health` returns 200.

## Definition of done

- `docker-compose up` brings up db + minio + api; `curl /health` returns 200.
- `pytest` passes with the health smoke test.
- pgvector extension is enabled in the db container.
- CI workflow is green on a trivial commit.

## Do NOT

- Add any models, business logic, LLM calls, or frontend code yet.
- Add a separate vector database — pgvector lives inside Postgres per `AGENTS.md` §3.

## On completion

Tick **P00** in `AGENTS.md` §7 and append a note to `reference/build-log.md`.
