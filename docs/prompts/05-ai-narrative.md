# P05 — AI Narrative Generation (LLM writes prose ONLY)

**Before starting:** read `AGENTS.md` (§5 — determinism boundary and "everything the LLM writes is reviewable"). Depends on P03 (RAG) and P04 (templates).

## Goal

Fill the narrative slots defined by the section map — and *only* those — with grounded, cited prose. The LLM never emits numbers a regulator cross-checks, never invents section structure, and never produces the folder/TOC/XML.

## Tasks

1. **LLM client** (`app/llm/`) — the provider-abstracted interface from `AGENTS.md` §3: `generate(system, messages, ...) -> text`. Backend and model name from config. No model name hard-coded in services.
2. **Narrative service** (`services/narrative/generate.py`):
   - Input: project + section number + a specific narrative slot.
   - Retrieve grounding context from the KB (P03) relevant to that section (e.g. for `3.2.P.8` stability narrative, retrieve ICH Q1 chunks).
   - Build a tightly-scoped prompt: give the model the *structured data* (as facts it must not contradict), the *retrieved guidance* (with sources), and a strict instruction to write only the prose for this slot, in regulatory register, without inventing figures, dates, or claims not supported by the data.
   - Return prose + the list of KB sources used.
3. **Guardrails:**
   - Post-generation check: scan output for numbers/units and flag any that don't appear in the source data (surface as a warning for human review; do not silently trust). The determinism boundary means numbers should come from data slots, not prose — this catches leakage.
   - Length bounds per slot.
   - No fabricated citations: the model may only reference sources actually retrieved.
4. **Audit trail** (`narrative_generation` table): store project, section, slot, model name, the retrieved context (or its IDs), the final prompt, the output, timestamp, and the human status (pending/approved/edited). This is required by `AGENTS.md` §5.
5. **API**: `POST /projects/{id}/sections/{sec}/narrative/{slot}:generate` → returns draft + sources + audit id. `POST .../approve` and `.../edit` to set human status.
6. **Wire into templating**: the P04 context builder can now pull *approved* narrative for a slot; unapproved slots render as visible "DRAFT — not approved" placeholders so nothing unreviewed reaches a package.
7. **Tests**: generation for a stability slot returns prose citing the seeded ICH source; the number-leakage guardrail flags an injected inconsistent figure; only approved narrative reaches a rendered section.

## Definition of done

- Narrative slots fill with grounded, cited prose stored with a full audit trail.
- Guardrails flag numeric leakage and block fabricated citations.
- Only human-approved narrative is used in rendered sections.

## Do NOT

- Let the LLM generate section numbers, TOC entries, folder paths, checksums, tables of figures, or XML. Ever.
- Use narrative that hasn't been through the approve/edit step in a real package.

## On completion

Tick **P05** in `AGENTS.md` §7; append to `reference/build-log.md`.
