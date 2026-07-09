# Build Log

Append a short entry as each phase is completed: what was built, key decisions,
and one concept to revisit. Newest at the top.

---

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
