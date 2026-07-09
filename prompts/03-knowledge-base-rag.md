# P03 — Regulatory Knowledge Base + RAG (copyright-safe)

**Before starting:** read `AGENTS.md` (§3, §5 — the copyright rule especially). Depends on P00–P02.

## Goal

Build a retrieval layer so the narrative generator (P05) and the AI reviewer (P10) can ground their output in actual regulatory guidance, instead of the LLM relying on memory. Uses pgvector inside the existing Postgres.

## Hard rule (non-negotiable)

**Only ingest freely-redistributable guidance.** ICH guidelines (M4, Q1, Q2, Q3, Q6, etc.) and most agency guidance documents are fine. **Pharmacopoeias (USP, Ph. Eur., BP) are copyrighted — do NOT ingest their monograph text.** The KB may store a *citation/reference* to a pharmacopoeial monograph (title, version, section) but not its content. Enforce this at ingestion time: an allowlist of permitted sources, and a `license` field on every document that must be set to a redistributable value or the ingest is rejected.

## Tasks

1. **Schema** (new migration): `kb_document` (source, title, version, url, license, jurisdiction) and `kb_chunk` (document_id, ordinal, text, `embedding vector(N)`, section_label). Add a pgvector index (HNSW or IVFFlat).
2. **Ingestion pipeline** (`services/knowledge/ingest.py`):
   - Input: a PDF/text guideline + metadata including `license` and `source`.
   - Reject if `source` not in the allowlist or `license` not redistributable.
   - Chunk (respect headings/sections; keep section labels), embed via the abstracted embedding client, store chunks.
   - Idempotent: re-ingesting the same document version updates rather than duplicates.
3. **Embedding client** — provider-abstracted like the LLM client (config-selected model). Interface: `embed(texts) -> vectors`.
4. **Retrieval service** (`services/knowledge/retrieve.py`): `search(query, k, filters)` → top-k chunks with source + section, filterable by jurisdiction and source. Return enough metadata for citation.
5. **Seed the KB** with a few genuinely redistributable ICH guideline PDFs (document them in the build log with their source URLs). If you can't fetch a document, stub the ingest with a small placeholder text file and mark it clearly — do not fabricate guideline content.
6. **API**: `POST /kb/ingest` (admin), `GET /kb/search?q=`.
7. **Tests**: allowlist/license enforcement rejects a disallowed source (e.g. a "USP monograph"); ingest→search round-trip returns the expected chunk; re-ingest doesn't duplicate.

## Definition of done

- A permitted ICH guideline ingests and is retrievable by semantic query with source+section metadata.
- Attempting to ingest a pharmacopoeial monograph is rejected by the license gate, with a test proving it.
- pgvector search returns ranked, cited chunks.

## Design notes

- Every retrieved chunk must be traceable to source + section so downstream generation can cite it and a human can verify. Retrieval that can't be cited is not useful here.
- Keep `k` and similarity thresholds in config.

## On completion

Tick **P03** in `AGENTS.md` §7; append to `reference/build-log.md`, listing exactly which guideline sources you ingested and their licenses.
