# P01 — Data Model (the single source of truth)

**Before starting:** read `AGENTS.md` (§5, §6) — especially the determinism boundary. Every value a regulator cross-checks lives here and is produced by code, never by the LLM.

## Goal

Model the canonical entities in `AGENTS.md` §6 as SQLAlchemy models, generate the Alembic migration, and mirror them as Pydantic schemas. This model is what templates and builders read from.

## Tasks

1. **SQLAlchemy models** in `app/models/` for each entity in `AGENTS.md` §6:
   - `Product`, `Manufacturer`, `ActiveIngredient` (API), `Excipient`, `Packaging`, `Stability`, `Clinical`, `Project`, `Sequence`.
   - Relationships: a `Project` belongs to one `Product` and a target **region profile** (store region as an enum/string: `NAFDAC`, `FDA`, `EU`); a `Product` has many manufacturers, APIs, excipients, packaging entries, stability studies, clinical entries; a `Project` has many `Sequence`s (`0000`, `0001`…).
   - Use UUID primary keys. Add `created_at`/`updated_at` timestamps. Add sensible nullability — regulatory data is often partial early on, so most fields are nullable but typed.
   - Model enums explicitly (registration type: new/renewal/variation; legal status; GMP status; compendial status; dosage form as a controlled list you can extend).
2. **Field coverage** — capture at least every field listed in `AGENTS.md` §6. For `Stability`, model each study as a row (type = accelerated/long-term/intermediate) with condition, duration, and a results summary, so the validation engine (P06) can compare declared shelf life against supported duration.
3. **Pydantic schemas** in `app/schemas/` — `Create`, `Update`, and `Read` variants per entity. `Read` includes nested children where useful for document generation.
4. **Alembic migration** generating the full schema. Verify it applies cleanly against the P00 database.
5. **Seed script** (`scripts/seed_demo.py`) that inserts one realistic demo product (e.g. a generic tablet) with manufacturer, one API, a couple of excipients, packaging, two stability studies (one supporting 24 months, product shelf-life declared 36 — deliberately inconsistent so P06 has something to catch), and a bioequivalence clinical entry.
6. **Tests**: models create/read round-trip; the migration applies; the seed script runs.

## Definition of done

- Migration applies cleanly; `scripts/seed_demo.py` populates a full demo project.
- Pydantic `Read` schemas can serialize a full nested product.
- Tests pass.

## Design notes

- Keep a `region` field on `Project` — it drives which Module 1 and which builder run later. Do not branch on region in the models themselves.
- The deliberately-inconsistent shelf-life demo data is intentional: it's the fixture P06's rule engine will validate against. Leave it.

## On completion

Tick **P01** in `AGENTS.md` §7; append to `reference/build-log.md`.
