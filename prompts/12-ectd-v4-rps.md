# P12 — eCTD v4.0 (HL7 RPS) — Future / Optional

**Before starting:** read `/reference/ectd-backbone-architecture.md` (v4.0 section) and `AGENTS.md` §2 target #3. **Do not start this until P00–P10 are solid, tested, and a real v3.2.2 submission has been validated.** This is a large, separable addition, not a quick follow-on.

## Reality check first

Before building, **re-verify the current state** (formats change): is v4.0 now mandatory-only for your target agency, or is v3.2.2 still accepted? As of this kit's snapshot, FDA accepts *both* v3.2.2 and v4.0 for new applications and has not set a v4.0-only date. Only invest here when a target market actually requires or benefits from v4.0. Check the agency's eCTD pages and Data Standards Catalog.

## Goal

Add a `V4RpsBackboneBuilder` behind the P09 `BackboneBuilder` interface, so v4.0 packages can be produced from the same assembled leaf inventory without disturbing the v3.2.2 path.

## Tasks

1. **Study the spec** — HL7 RPS message structure, the ICH eCTD v4.0 Implementation Guide, controlled-vocabulary packages, and the region's v4.0 Module 1 implementation guide. Capture key structural notes in a new `/reference/ectd-v4-rps.md`.
2. **RPS message builder** — a single RPS XML message (not the twin ICH+regional DTD backbones): documents, keywords, and **context-of-use (CoU)** elements, each identified by **UUID**; priority ordering; lifecycle at the CoU level.
3. **UUID management** — persist UUIDs for documents/CoUs/keywords across sequences so reuse and lifecycle operations resolve correctly (model these in the DB).
4. **Controlled vocabularies** — load the versioned CV packages from config; validate envelope/keyword values against them.
5. **Validation** — extend P10 with v4.0-specific checks (RPS schema validity, UUID integrity, CoU lifecycle integrity), plus external-validator integration for the authoritative pass.
6. **Parity tests** — the same demo project produces both a valid v3.2.2 sequence (P09) and a valid v4.0 message, from one assembly, with the interface swapped by config only.

## Definition of done

- v4.0 packages build from the shared leaf inventory via the swappable builder interface.
- UUID and CoU lifecycle integrity are modeled, persisted, and validated.
- v3.2.2 path is entirely unaffected.

## Do NOT

- Refactor the v3.2.2 path to accommodate v4.0 — they coexist behind the interface.
- Start before earlier phases are production-solid.

## On completion

Tick **P12** in `AGENTS.md` §7; append to `reference/build-log.md`.
