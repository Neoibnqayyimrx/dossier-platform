"""AI reviewer (P10) -- the *additive* layer. Reads each section's
APPROVED narrative text (P05's `get_approved_narrative`, the same
structured, already-audited text P07 renders into the actual PDF -- not a
re-extraction from the built PDF, which would be strictly worse data
reached the harder way) and asks the LLM to flag soft, contextual concerns
no deterministic rule could ever catch: an omitted robustness discussion,
a pharmacopoeia version worth double-checking, a narrative that never
mentions the intermediate storage condition.

Every finding this produces is `Severity.ADVISORY` -- not by convention,
by construction: nothing in this module can ever emit `Finding(severity=
Severity.ERROR, ...)`, so it is structurally incapable of gating an
export, matching AGENTS.md's "never let the AI reviewer override
deterministic checks."

Grounding discipline matches P05 exactly: the model may cite ONLY sources
we actually retrieved and handed it, in a fixed `[Source: ...]` marker
format -- any output line that doesn't match that exact shape is dropped,
never surfaced as a citation-free finding.
"""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.embeddings import EmbeddingClient, get_embedding_client
from app.knowledge.retrieve import SearchResult, search
from app.llm.client import LLMClient, get_llm_client
from app.models.project import Project
from app.narrative.context import get_approved_narrative
from app.templating.registry import SECTIONS
from app.validation.engine import Finding, Severity

SOURCE = "ai-reviewer"

SYSTEM_PROMPT = (
    "You are reviewing ALREADY-APPROVED narrative text from a pharmaceutical "
    "regulatory dossier (CTD format) for soft, contextual concerns a deterministic "
    "checklist could never catch -- omissions, things worth double-checking, "
    "content that doesn't match current guidance. You are NOT checking facts, "
    "numbers, or citations for correctness -- that's already done. Rules, strictly "
    "enforced:\n"
    "- Output one issue per line, exactly in this format: "
    "'ISSUE: <concern, one sentence> [Source: <title> <version>]'.\n"
    "- You may cite ONLY the sources listed under SOURCES, using exactly that "
    "marker format. Never cite anything else, and never emit an issue with no "
    "citation.\n"
    "- If you have no concerns, output exactly: NO ISSUES\n"
    "- Never invent facts, numbers, or requirements not grounded in the SOURCES."
)

# "ISSUE: <text> [Source: <title> <version>]" -- strict on purpose; any
# line that doesn't match this exact shape (including a citation-free
# issue) is silently dropped, never surfaced as a finding. Same
# discipline as app.narrative.guardrails' citation marker parsing.
_ISSUE_RE = re.compile(r"^ISSUE:\s*(?P<text>.+?)\s*\[Source:\s*(?P<citation>[^\]]+)\]\s*$")


def _build_prompt(section_title: str, narrative_text: str, sources: list[SearchResult]) -> str:
    source_labels = [f"{result.title} {result.version}" for result in sources]
    source_block = (
        "\n".join(f"- {label}: {result.text}" for label, result in zip(source_labels, sources))
        or "(no relevant guidance retrieved)"
    )
    return (
        f"SECTION: {section_title}\n\n"
        f"APPROVED NARRATIVE TEXT:\n{narrative_text}\n\n"
        f"SOURCES:\n{source_block}\n\n"
        f"Review this narrative now."
    )


def _parse_issues(response: str, section: str) -> list[Finding]:
    findings: list[Finding] = []
    for line in response.splitlines():
        match = _ISSUE_RE.match(line.strip())
        if not match:
            continue
        findings.append(
            Finding(
                rule_id="AI00",
                severity=Severity.ADVISORY,
                category="ai-review",
                message=f"{match.group('text')} [Source: {match.group('citation')}]",
                section=section,
                source=SOURCE,
            )
        )
    return findings


async def review_narratives(
    db: AsyncSession,
    project: Project,
    *,
    llm: LLMClient | None = None,
    embedding_client: EmbeddingClient | None = None,
    k: int = 3,
) -> list[Finding]:
    llm = llm or get_llm_client()
    embedding_client = embedding_client or get_embedding_client()

    findings: list[Finding] = []
    for number, spec in SECTIONS.items():
        if not spec.narrative_slots:
            continue
        narrative = await get_approved_narrative(db, project.id, number)
        if not narrative:
            continue
        narrative_text = "\n\n".join(narrative.values())

        sources = (
            await search(db, embedding_client, spec.grounding_query, k=k)
            if spec.grounding_query
            else []
        )
        prompt = _build_prompt(spec.title, narrative_text, sources)
        response = llm.generate(SYSTEM_PROMPT, [{"role": "user", "content": prompt}])
        findings.extend(_parse_issues(response, section=number))

    return findings
