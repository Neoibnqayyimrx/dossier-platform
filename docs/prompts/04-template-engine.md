# P04 — Section Template Engine (deterministic fill)

**Before starting:** read `AGENTS.md` (§5 determinism boundary, §6). Depends on P01–P02.

## Goal

Turn structured product data into CTD section documents via templates, where **only clearly-delimited narrative blocks** are left for the LLM. Everything else is filled deterministically from the data model.

## Concept

A CTD section is a `docxtpl` template with two kinds of slots:

- **Data slots** — `{{ product.brand_name }}`, `{{ product.strength }}`, `{{ api.name }}` — filled directly from the P01 model. Deterministic.
- **Narrative slots** — explicitly marked regions, e.g. a context variable `narrative_description` rendered where the section needs prose. These are the *only* places P05's LLM output lands. In the template author's source, mark them visibly, e.g. a comment block `{# AI: 3.2.P.1 description #}`.

## Tasks

1. **Section map** (`services/templating/section_map.py`) — a declarative registry mapping CTD section numbers (e.g. `3.2.P.1`, `3.2.S.1.1`, `1.0` cover letter, `2.3` QOS) to: a template file, the data entities it needs, and the list of narrative slots it exposes. This map is the backbone of assembly (P07/P08 iterate over it).
2. **Templates** (`backend/templates/`) — author an initial, representative set of `docxtpl` templates. Start with: cover letter (1.0), a Module 1 application-info doc, `3.2.P.1` (description & composition), `3.2.P.5.1` (specifications, largely tabular/deterministic), a stability summary section, and `2.3` QOS skeleton. Tables (composition, specs, stability) are built from data, not prose.
3. **Context builder** (`services/templating/context.py`) — given a project + section number, assemble the docxtpl context dict from the data model (products, APIs, excipients, packaging, stability, etc.), with narrative slots left empty/placeholder for now.
4. **Renderer** (`services/templating/render.py`) — render a section template + context → a `.docx` in object storage; return a handle. Deterministic output (see P07 for PDF determinism; keep DOCX generation stable too).
5. **Composition & specification tables** must be generated from data rows, correctly totaling (e.g. composition percentages), so the validation engine can later check them.
6. **Tests**: rendering `3.2.P.1` for the demo product produces a DOCX containing the correct brand name, strength, and a composition table matching the seed data; narrative slots render as clearly-marked placeholders.

## Definition of done

- Each registered section renders to a DOCX with all data slots correctly filled from the model.
- Narrative slots are present, empty, and clearly identifiable (ready for P05).
- The section map lists every implemented section with its data deps and narrative slots.

## Do NOT

- Call the LLM here. Narrative slots stay empty placeholders until P05.
- Hard-code any product-specific values into templates — everything data-driven.

## On completion

Tick **P04** in `AGENTS.md` §7; append to `reference/build-log.md` listing which sections have templates.
