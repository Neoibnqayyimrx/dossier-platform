# P10 — eCTD Validation (business rules + validator integration + AI reviewer)

**Before starting:** read `/reference/ectd-backbone-architecture.md` (Validation section) and `AGENTS.md` §5. Depends on P09. This is what stops a package from being rejected at the gateway.

## Goal

Validate a built eCTD sequence against mechanical business rules and (where possible) an agency-recognized external validator, plus add the *additive* LLM "AI reviewer" for softer issues. Nothing here replaces the deterministic P06 rules — this layer sits on top of the built package.

## Tasks

1. **Mechanical eCTD validators** (`services/ectd/validate.py`), each a testable rule:
   - `index.xml` and regional XML are **DTD-valid** (re-check post-build).
   - Every `<leaf>` checksum matches the actual file's MD5; `index-md5.txt` matches `index.xml`.
   - Every `xlink:href` resolves to a file that exists; no orphan files not referenced by a leaf.
   - Lifecycle integrity: every `modified-file` resolves to a real leaf in a prior sequence with a matching ID; no `replace`/`delete` targeting a non-existent or already-deleted leaf.
   - Granularity/naming/structure: folder layout, file naming, and PDF specs (searchable, no encryption, fonts embedded) conform.
   - Required-leaf presence for the region profile and submission type.
2. **External validator integration (optional but recommended):** provide an adapter interface so a recognized validator (e.g. an eValidator-class tool) can be invoked and its report parsed. If none is available in the environment, clearly label our own report as "internal checks only — run an agency-recognized validator before submission." **Never claim gateway-readiness from internal checks alone.**
3. **AI reviewer** (`services/ectd/ai_review.py`) — the *additive* layer: using the KB (P03), have the LLM flag softer, contextual issues (e.g. "method validation appears to omit robustness", "specification cites an older pharmacopoeia version — verify current", "stability narrative doesn't mention intermediate condition"). Output is **advisory warnings for human review**, clearly separated from deterministic errors, each with its grounding citation. It never gates on its own and never overrides deterministic results.
4. **Consolidated report:** merge P06 (data), mechanical eCTD (this phase), external validator (if present), and AI-reviewer outputs into one report with clear provenance and severity per finding.
5. **API**: `POST /projects/{id}/validate/ectd?region=FDA` → consolidated report.
6. **Tests:** a deliberately corrupted sequence (wrong checksum, dangling `modified-file`, orphan file, encrypted PDF) is caught by the matching rule; a clean sequence passes mechanical checks; the AI reviewer's findings are labeled advisory and carry citations.

## Definition of done

- The mechanical validator catches checksum, DTD, orphan, and lifecycle-integrity faults with targeted messages.
- Reports clearly separate deterministic errors from advisory AI findings, and never overstate gateway-readiness.
- Tests cover each mechanical rule with a failing fixture.

## Do NOT

- Let the AI reviewer gate exports or override deterministic checks.
- Present internal validation as equivalent to the agency's own validator.

## On completion

Tick **P10** in `AGENTS.md` §7; append to `reference/build-log.md`.
