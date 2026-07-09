# LEARNING.md — Build it *and* learn it

This project is a course disguised as a codebase. You (the human) are an industrial pharmacist and software engineer; the goal is that by the end you understand **the software** (language, libraries, architecture) and **the regulatory domain** (what a dossier is, why every part exists) well enough to extend or rebuild any of it yourself.

This file tells both you and Claude Code how to make the build a learning experience. It pairs with the "Learning Mode" section in `AGENTS.md`.

---

## How to drive Claude Code so you actually learn

Start each phase with a message like:

> "Read `AGENTS.md`, `LEARNING.md`, and `prompts/06-validation-engine.md`. Before writing code, **teach me the plan**: what we're building, why, and the key decisions. Then build it in small pieces, explaining each. At the end, quiz me and give me one rule to write myself."

Good phrases to keep using:
- *"Explain the why before the code."*
- *"What language feature is that, and why use it here?"*
- *"Which part of this exists because a regulator requires it?"*
- *"Let me write this function — give me the signature and the intent, then review mine."*
- *"Quiz me before we move on."*
- *"Slow down — I don't understand X yet."*

And when you want speed instead: *"Just build this part, I'll read it after."*

## The two tracks you're learning

Every phase teaches something on **both** tracks. Here's the map so you can see the arc.

| Phase | Software you'll learn | Regulatory / dossier you'll learn |
|------|----------------------|-----------------------------------|
| P00 | Monorepos, containers, `docker-compose`, dependency management, env-based config, CI | How submissions are transported; CTD vs eCTD framing |
| P01 | Data modeling, ORMs (SQLAlchemy), migrations (Alembic), enums, relationships, schemas (Pydantic) | The data that *is* a dossier: product, API, excipients, stability, clinical — and how they relate |
| P02 | REST APIs, FastAPI, dependency injection, JWT auth, async/await | The application/sequence lifecycle; one dossier per product |
| P03 | Embeddings, vector search, pgvector, chunking, RAG | The guideline landscape: ICH M4/Q/E/S, agency guidance; what's copyrightable |
| P04 | Templating engines, Jinja/docxtpl, separating data from presentation | Section anatomy: what `3.2.P.1`, `2.3` QOS, a cover letter actually contain |
| P05 | LLM integration, prompt design, guardrails, audit trails | Regulatory writing register; why numbers must never come from prose |
| P06 | Rule engines, small testable units, domain validation, fixtures | Cross-consistency the way a reviewer checks it (shelf life vs stability, strength vs label) |
| P07 | Subprocess/headless tools, output determinism, PDF internals, bookmarks | eCTD PDF rules and document **granularity** (why not to merge) |
| P08 | Filesystem structure, packaging/ZIP, config-driven region profiles | Module 1–5 folder hierarchy; NAFDAC Module 1 contents; the TOC |
| P09 | XML with `lxml`, DTD validation, MD5 checksums, versioning/lifecycle logic, interfaces | The eCTD backbone: sequences, leaves, operations, `modified-file` — the diff layer |
| P10 | Layered validation, adapter pattern, integrating external tools | Agency validation criteria; why gateways reject; the AI reviewer's proper (limited) role |
| P11 | React/Next.js, state, forms, API clients, e2e tests | The data-first wizard philosophy; region-adaptive UX |
| P12 | Interfaces/polymorphism, UUID identity, implementing a formal spec | HL7 RPS, context-of-use, eCTD v4.0 |

## Recommended rhythm per phase

1. **Plan lesson** — Claude explains the what/why/decisions. You ask questions until it's clear.
2. **Guided build** — small pieces, each explained. You read, you interrupt, you ask "what's that syntax?"
3. **Your turn** — you implement one small piece yourself; Claude reviews it.
4. **Recap + quiz** — Claude summarizes both tracks, asks you 2–3 questions or sets a mini-exercise.
5. **Log it** — the phase note in `reference/build-log.md` includes a one-line "concept I want to revisit" from you.

Don't rush the checkpoints. The build finishing is not the goal; you being able to rebuild it is.

## Using your real dossier draft (when you post it)

Your finished dossier is the best possible teaching material. Once you post it (redacted of anything commercially confidential — proprietary process detail, DMF/API-supplier confidential info, third-party data, personal data in clinical), we'll use it three ways:

1. **Guided tour** — walk through it section by section against `/reference/dossier-anatomy.md`, so you learn what each module/section is *for* and what a reviewer looks for in it. You'll see the abstract structure made concrete in a document you know.
2. **Reverse-engineer the data model** — identify, for each section, which parts are *fixed boilerplate*, which are *product-specific data* (→ P01 model fields), and which are *narrative prose* (→ P05 LLM slots). This directly sharpens the P01/P04 design.
3. **Real fixtures** — turn (redacted) sections into golden test fixtures and starter `docxtpl` templates, so the platform is validated against something real rather than toy data.

When you post it, say which of these you want to start with — or just say "give me the guided tour."

## A note on how to learn the regulatory side

You know the pharmaceutical science. What this project teaches on top is the **submission craft**: how that science is *organized, cross-referenced, versioned, and transported* so a regulator can review it efficiently. That craft is exactly what turns a pile of correct documents into an accepted dossier — and it's the part software can most powerfully assist. Keep asking "why does the regulator want it *this* way?" — the answer is almost always "so a reviewer can find, trust, and track it," and that principle explains most of the format.
