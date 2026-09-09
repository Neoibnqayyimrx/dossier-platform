"""Narrative generation service (P05): fill one narrative slot with
grounded, cited prose, and record a full audit trail.

WHY guardrail checks run in this order (citations, then leakage): a
fabricated citation is a hard reject (raise before anything is persisted —
"block", per AGENTS.md §5), so it must run first. Numeric leakage is only
a warning attached to a row that otherwise exists, so it runs after and
never prevents the record from being created.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.knowledge.embeddings import EmbeddingClient, get_embedding_client
from app.knowledge.retrieve import SearchResult, search
from app.llm.client import LLMClient, get_llm_client
from app.models.kb import KBChunk
from app.models.narrative import NarrativeGeneration
from app.models.project import Project
from app.narrative.facts import render_facts
from app.models.enums import NarrativeRegister
from app.narrative.guardrails import (
    check_citations,
    check_numeric_leakage,
    check_patient_register,
)
from app.templating.context import build_context
from app.templating.registry import get_section

# The rules that hold whoever the reader is. Every one of them is a
# determinism-boundary rule (AGENTS.md 5) rather than a style rule, which
# is why they are shared and the register-specific half below is not.
_SHARED_RULES = (
    "- Write ONLY the requested prose -- no section numbers, headings, "
    "tables, or document structure.\n"
    "- Every figure, date, or quantity you use MUST already appear in the "
    "FACTS block below. Never invent or restate a number that isn't there.\n"
    "- You may cite ONLY the sources listed under SOURCES, using exactly "
    "the marker format '[Source: <title> <version>]'. Never cite anything "
    "else.\n"
)

# P23: one system prompt per register.
#
# WHY two prompts and not one with a sentence appended: the two documents
# ask for genuinely different work. An SmPC section is written FOR a
# prescriber, in the vocabulary of the field. A patient leaflet section is a
# TRANSLATION of facts the filer has already stated, for a reader who has
# never seen them -- different audience, different verb, different sentence
# length. Bolting "and make it simple" onto a regulatory prompt produces
# regulatory prose with short words in it, which is the failure mode the
# whole readability obligation exists to prevent.
#
# The prompt is only half of the mechanism. `check_patient_register` judges
# what actually came back, because a prompt is an instruction a model may
# ignore silently -- see SectionSpec.narrative_register.
SYSTEM_PROMPTS: dict[NarrativeRegister, str] = {
    NarrativeRegister.REGULATORY: (
        "You are drafting one narrative paragraph for a pharmaceutical regulatory "
        "dossier (CTD format). Rules, strictly enforced:\n"
        + _SHARED_RULES
        + "- Write in a formal regulatory register."
    ),
    NarrativeRegister.PATIENT: (
        "You are drafting one section of a PATIENT INFORMATION LEAFLET -- the "
        "printed insert a patient reads at home, not a document for a doctor or "
        "a regulator. Rules, strictly enforced:\n"
        + _SHARED_RULES
        + "- Address the reader directly as 'you'.\n"
        "- Use everyday words. Never write 'contraindicated' (say 'must not be "
        "used'), 'adverse reaction' (say 'side effect'), 'hepatic' (say "
        "'liver'), 'renal' (say 'kidney'), 'administer' (say 'take'), or "
        "'concomitant' (say 'at the same time').\n"
        "- Keep every sentence under 25 words, carrying one idea.\n"
        "- Do not soften or omit anything: a leaflet must state every warning "
        "the prescribing information states, in plain words."
    ),
}

# Kept as the regulatory prompt's old name so that nothing importing it
# breaks. It is the default register, and the one every section other than
# the leaflet uses.
SYSTEM_PROMPT = SYSTEM_PROMPTS[NarrativeRegister.REGULATORY]


def _build_prompt(
    section_title: str, slot: str, facts_text: str, sources: list[SearchResult]
) -> tuple[str, list[str]]:
    source_labels = [f"{result.title} {result.version}" for result in sources]
    source_block = (
        "\n".join(f"- {label}: {result.text}" for label, result in zip(source_labels, sources))
        or "(no relevant guidance retrieved)"
    )
    prompt = (
        f"SECTION: {section_title}\n"
        f"NARRATIVE SLOT: {slot}\n\n"
        f"FACTS:\n{facts_text}\n\n"
        f"SOURCES:\n{source_block}\n\n"
        f"Write the '{slot}' narrative for this section now."
    )
    return prompt, source_labels


@dataclass
class GenerationResult:
    narrative: NarrativeGeneration
    warnings: list[str]


async def generate_narrative(
    db: AsyncSession,
    project: Project,
    section_number: str,
    slot: str,
    *,
    embedding_client: EmbeddingClient | None = None,
    llm_client: LLMClient | None = None,
    k: int | None = None,
) -> GenerationResult:
    """Generate, guardrail-check, and persist one narrative slot's draft.

    Raises `NarrativeGuardrailError` (no row persisted) if the model cites
    a source that wasn't actually retrieved. Numeric-leakage findings are
    non-blocking and stored on the returned/persisted row instead.
    """
    section = get_section(section_number)
    if slot not in section.narrative_slots:
        raise ValueError(
            f"{slot!r} is not a narrative slot of section {section_number!r}; "
            f"declared slots: {', '.join(section.narrative_slots)}"
        )

    settings = get_settings()
    embedding_client = embedding_client or get_embedding_client()
    llm_client = llm_client or get_llm_client()
    k = k or settings.kb_search_default_k

    context = build_context(section_number, project)
    facts_text = render_facts(context)

    results: list[SearchResult] = []
    if section.grounding_query:
        results = await search(db, embedding_client, section.grounding_query, k=k)

    prompt, source_labels = _build_prompt(section.title, slot, facts_text, results)
    output = llm_client.generate(
        system=SYSTEM_PROMPTS[section.narrative_register],
        messages=[{"role": "user", "content": prompt}],
    )

    check_citations(output, source_labels)  # raises on a fabricated citation
    warnings = check_numeric_leakage(output, facts_text)
    # P23: and, for a leaflet, whether it reads like one. Warnings, not a
    # raise, for the reason check_patient_register's docstring gives -- a
    # draft with three phrases flagged on it is more use to a reviewer than
    # an error and no draft.
    if section.narrative_register is NarrativeRegister.PATIENT:
        warnings.extend(check_patient_register(output))

    chunks: list[KBChunk] = []
    chunk_ids = [uuid.UUID(result.chunk_id) for result in results]
    if chunk_ids:
        chunks = list((await db.scalars(select(KBChunk).where(KBChunk.id.in_(chunk_ids)))).all())

    record = NarrativeGeneration(
        project_id=project.id,
        section_number=section_number,
        slot=slot,
        model_name=settings.llm_model,
        prompt=prompt,
        output=output,
        warnings="\n".join(warnings) or None,
        sources=chunks,
    )
    db.add(record)
    await db.commit()
    # NOTE: no db.refresh() here on purpose -- this session has
    # expire_on_commit=False, so `record` (including the `sources` list we
    # just assigned) stays fully populated in memory after commit.
    # Refreshing would expire `sources` back to a lazy relationship, which
    # can't be re-loaded outside an awaited call -- exactly the trap
    # `record.id`'s Python-side `default=uuid.uuid4` (app/models/base.py)
    # exists to avoid needing a round-trip for in the first place.
    return GenerationResult(narrative=record, warnings=warnings)
