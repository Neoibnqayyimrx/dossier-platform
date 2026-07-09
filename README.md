# Dossier Platform

A pharmaceutical **CTD/eCTD dossier platform** — plan, teaching materials, and a
working first slice of code, all in one repo. Built to be developed with Claude
Code, while you learn the software *and* the regulatory domain as you go.

## What's here

This repo is two things at once:

1. **A plan you build against** — `AGENTS.md` (master context), `prompts/`
   (phase-by-phase build prompts P00–P12), `reference/` (regulatory background),
   and `LEARNING.md` (how to learn while building).
2. **Actual working code** — `app/`, `tests/`, `run_demo.py`: a runnable
   vertical slice (data model → template → validation) built from a real
   dossier (LAMOX, Amoxicillin 500 mg capsules).

## Run the working slice first (2 minutes)

```bash
pip install -r requirements.txt
python run_demo.py      # seeds LAMOX, validates it, renders section 3.2.P.1
pytest -q               # 6 tests
```

`run_demo.py` catches three *real* copy-paste bugs in the LAMOX dossier
(wrong strength, wrong dosage form, a leftover reference to a different
product), then shows a clean pass once corrected. That's the whole platform's
value proposition, demonstrated on real content.

## Then build the rest with Claude Code

Open this repo in Claude Code and work the phases in order. Start each with:

> "Read `AGENTS.md`, `LEARNING.md`, and `prompts/00-repo-scaffold.md`. Teach me
> the plan before writing code, then build it."

`AGENTS.md` is read automatically as project context. It contains a **Learning
Mode** that makes Claude Code teach as it builds. Tick the Build Status boxes in
`AGENTS.md` and append to `reference/build-log.md` as you complete phases.

## Map of the repo

```
AGENTS.md                     master context (read first) + Learning Mode
LEARNING.md                   how to learn while building; software+regulatory curriculum
prompts/                      P00-P12 build prompts, one per phase
reference/
  dossier-anatomy.md          guided tour of CTD Modules 1-5
  nafdac-vs-fda-ema-scope.md  what each regulator requires; why NAFDAC-CTD first
  ectd-backbone-architecture.md   the eCTD v3.2.2 XML backbone in detail
  worked-example-lamox.md     the real LAMOX dossier mapped to model/rules/templates
  build-log.md                running log of what's built (append as you go)
app/                          THE CODE (the working slice)
  models/                     SQLAlchemy 2.x data model (P01)
  templating/                 section rendering from data (P04)
  validation/                 deterministic rule engine + rules R01-R06 (P06)
  seed/                       LAMOX seed data (buggy + corrected)
tests/                        pytest suite
run_demo.py                   end-to-end demonstration
requirements.txt
```

## Where the slice fits in the phase plan

The code in `app/` is a partial, runnable start on three phases:

- **P01 (data model)** — real models in `app/models/`, running on SQLite for
  portability. When you do P00/P02 (docker-compose + Postgres + FastAPI), the
  same models point at Postgres — only the connection string changes.
- **P04 (templating)** — `app/templating/section_map.py` renders 3.2.P.1 from
  structured data. Next step: turn it into a real `docxtpl` .docx template.
- **P06 (validation)** — `app/validation/` with six rules. Next step: grow the
  rule set and wire it behind the FastAPI `/readiness` endpoint (P02).

So the slice isn't throwaway — it's the seed the later phases grow around.

## The one rule to remember

**The AI writes narrative prose only. Everything a regulator cross-checks is
deterministic code.** If any phase drifts from that, it's wrong.

## A caution worth keeping

Regulatory formats change. Before relying on any regulator-specific output for a
real submission, confirm the current requirement on the agency's own site
(NAFDAC NAPAMS portal; FDA eCTD pages; EMA eSubmission). Region rules live in
config, not scattered through the code, precisely to make that easy.
