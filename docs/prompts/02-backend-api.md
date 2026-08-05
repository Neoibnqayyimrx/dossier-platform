# P02 — Backend API Skeleton (CRUD, auth, projects & sequences)

**Before starting:** read `AGENTS.md` (§4, §6). Depends on P01.

## Goal

Expose the data model over a clean FastAPI so the wizard (P11) and the builders have something to read/write. Add minimal auth and the project/sequence lifecycle.

## Tasks

1. **Routers** in `app/api/` — REST CRUD for every entity: products (+ nested manufacturers/APIs/excipients/packaging/stability/clinical), projects, sequences. Use the Pydantic schemas from P01. Async endpoints, dependency-injected DB session.
2. **Project endpoints** beyond CRUD:
   - `POST /projects/{id}/sequences` — create the next sequence (`0000`, then `0001`…), auto-numbered, zero-padded to 4 digits.
   - `GET /projects/{id}/readiness` — placeholder returning `{ready: false, checks: []}` for now; P06 fills it in.
3. **Auth** — keep it simple but real: JWT bearer, a `users` table, `POST /auth/login`, password hashing (argon2/bcrypt). Protect write endpoints; reads can require auth too. Don't gold-plate — no OAuth providers yet.
4. **Validation of input** — reject malformed enums, negative durations, etc., at the schema layer.
5. **Consistent errors** — a small error envelope; 404/409/422 used correctly.
6. **OpenAPI** — ensure the auto-docs are clean and every route is tagged by resource.
7. **Tests** (`httpx` + `pytest-asyncio`): full CRUD round-trip for a product with nested children; sequence auto-numbering; auth blocks unauthenticated writes.

## Definition of done

- A client can create a full product with all children via the API, list it, update it, and create sequences `0000`/`0001`.
- Unauthenticated writes are rejected; login issues a working token.
- Tests pass; OpenAPI docs render.

## Do NOT

- Put any document generation, templating, or LLM logic here — those are services called later, not API concerns yet.
- Branch on region in endpoints; region is just data on the project.

## On completion

Tick **P02** in `AGENTS.md` §7; append to `reference/build-log.md`.
