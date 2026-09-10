"""What this project's dossier owes, and the questions only the filer can
answer (P17).

WHY this endpoint exists at all: until now the answer to "what does this
dossier still owe?" existed only in a terminal, as the output of
`scripts/check_target_toc.py`. That is fine for the team building the
platform and useless to the regulatory affairs officer actually assembling
a filing. This serves the same resolution the builder uses, so the screen
and the built package can never describe different dossiers.

WHY the section list is served rather than assembled in TypeScript: the
same reason `/enums`, `/sections` and `/regions` are (see those routers).
The applicability table is regulatory config; a hand-maintained copy in the
frontend is a copy that drifts, and here it would drift into telling a
filer that a section they owe is not applicable.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_db, require_project_owner

# Reusing the projects router's own loader (underscored, but deliberately
# shared): it applies PROJECT_CHILD_OPTIONS, and a project loaded without
# those eager options would lazy-load inside an async request and blow up.
# One loader beats two that must be kept identical.
from app.api.routers.projects import _get_project_or_404
from app.ctd.region_profiles import REGION_PROFILES, Applicability, resolve_applicability
from app.ctd.toc import MODULE_TOC_LEAVES
from app.models.project import Project
from app.templating.instances import expand_sections
from app.target_toc import NA_STATEMENT_PRODUCTION

router = APIRouter(prefix="/projects", tags=["applicability"])

# The four states a leaf can be in, from the filer's point of view. These
# are deliberately NOT the same vocabulary as `Applicability` (which says
# what the guideline requires): a leaf can be REQUIRED and produced, or
# REQUIRED and outstanding, and the difference between those two is the
# only thing anyone looks at this screen to learn.
STATUS_PRODUCED = "produced"
STATUS_NOT_APPLICABLE = "not-applicable"
STATUS_PLACEHOLDER = "placeholder"
STATUS_OUTSTANDING = "outstanding"


class SectionCopyRead(BaseModel):
    """One COPY of a repeated section (P19).

    WHY the screen needs these at all: a product with two actives owes two
    complete 3.2.S.1 documents, and a list showing one row per section
    number tells the filer their dossier is half the size it is. The
    package builder has always known this (app.templating.instances); the
    screen did not, which is precisely the "the screen and the built
    package describe different dossiers" failure this router exists to
    prevent.
    """

    key: str
    subject: str


class SectionStatusRead(BaseModel):
    number: str
    module: int
    title: str
    applicability: Applicability
    status: str
    # Present iff applicability is CONDITIONAL: the question to put to the
    # filer, and their answer (null = not answered yet, which rule R19
    # reports as a WARNING).
    condition: str | None = None
    answer: bool | None = None
    # Present iff the leaf is being filed as a not-applicable statement.
    citation: str | None = None
    # P19. `repeat` names the axis (the same string the target TOC uses);
    # `copies` is what this project actually owes along it. Empty for a
    # section that appears once -- the common case, and the one where a
    # list of one copy would be noise.
    repeat: str | None = None
    copies: list[SectionCopyRead] = Field(default_factory=list)


class ConditionAnswersUpdate(BaseModel):
    """Answers to conditional sections, keyed by section number.

    A PATCH-style merge, not a replace: the UI answers one question at a
    time, and sending the whole map back on every click would let two people
    editing one project silently undo each other's answers. To retract an
    answer, send null for that number -- distinct from `false`, which is a
    positive statement that the section does not apply and produces a leaf.
    """

    answers: dict[str, bool | None] = Field(default_factory=dict)


def _status_for(resolved, produced: set[str]) -> str:
    if resolved.owes_statement:
        return STATUS_NOT_APPLICABLE
    if resolved.number in produced:
        return STATUS_PRODUCED
    # A leaf whose production type is `uploaded` has, at best, a
    # placeholder standing where a third-party document belongs -- the CPP
    # the regulator issued, the CRO's study report. Reporting that as
    # "produced" is the one thing this screen must never do, for the same
    # reason `scripts/check_target_toc.py` refuses to credit it: a
    # placeholder that reads as a finished document launders the platform's
    # largest gap into a green tick.
    if resolved.section.production == "uploaded":
        return STATUS_PLACEHOLDER
    return STATUS_OUTSTANDING


def _section_statuses(project: Project) -> list[SectionStatusRead]:
    # What the platform would actually put in the package right now, asked
    # of the same function the builder calls. A statement leaf is in here
    # too, which is why `owes_statement` is checked first above -- it is
    # both produced AND not applicable, and "not applicable" is the more
    # informative of the two.
    instances = [i for i in expand_sections(project) if not i.spec.is_statement]
    # P22: a leaf that ACCOMPANIES an upload does not make its section
    # produced. 5.3.1.2's structured summary renders for every project,
    # and the leaf an assessor is looking for there is the CRO's study
    # report -- reporting the section as produced because the summary
    # exists would be the same green tick for a missing document that
    # `scripts/check_target_toc.py` refuses to award.
    produced = {i.number for i in instances if i.spec.leaf_suffix is None}

    # P24: the two production routes that are NOT registry sections, and so
    # were invisible to this screen.
    #
    # It was inviting a filer to attach a PDF for four tables of contents
    # and three declarations the platform generates. That is the inverse of
    # the failure this screen usually guards against -- not a gap read as
    # finished, but finished work read as a gap -- and it costs a filer
    # real time hunting for documents that already exist.
    #
    # The module TOCs (1.1, 2.1, 3.1, 5.1) are built from the placed
    # package, which is why they cannot be registry sections at all: a
    # table of contents is a function of the package, not of the project
    # (see app/ctd/toc.py).
    produced |= set(MODULE_TOC_LEAVES)

    # The declarations (1.2.4-1.2.6) are rendered by
    # app/templating/declarations.py from `Declaration` rows, so a leaf is
    # produced when the filing actually HAS that declaration -- not merely
    # because the region declares a leaf for it. A profile with no mapping
    # (EU today) contributes nothing, which is correct rather than
    # unfortunate: it has no declared leaf numbers to claim.
    profile = REGION_PROFILES.get(project.region)
    if profile is not None:
        held = {declaration.declaration_type for declaration in project.declarations}
        produced |= {
            number
            for declaration_type, number in profile.declaration_leaves.items()
            if declaration_type in held
        }

    copies: dict[str, list[SectionCopyRead]] = {}
    for instance in instances:
        if instance.subject is None:
            continue
        copies.setdefault(instance.number, []).append(
            SectionCopyRead(key=instance.key, subject=instance.subject_name)
        )
    repeats = {instance.number: instance.spec.repeat for instance in instances}

    return [
        SectionStatusRead(
            number=resolved.number,
            module=resolved.section.module,
            title=resolved.section.title,
            applicability=resolved.section.status,
            status=_status_for(resolved, produced),
            condition=resolved.section.condition,
            answer=resolved.answer,
            citation=(
                resolved.section.citation
                if resolved.section.production == NA_STATEMENT_PRODUCTION
                else None
            ),
            repeat=repeats.get(resolved.number),
            copies=copies.get(resolved.number, []),
        )
        for resolved in resolve_applicability(project).values()
    ]


@router.get("/{project_id}/section-status", response_model=list[SectionStatusRead])
async def get_section_status(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> list[SectionStatusRead]:
    """Every leaf this project's submission type declares, in CTD order."""
    project = await _get_project_or_404(project_id, db)
    return _section_statuses(project)


@router.patch("/{project_id}/conditions", response_model=list[SectionStatusRead])
async def answer_conditions(
    project_id: uuid.UUID,
    payload: ConditionAnswersUpdate,
    db: AsyncSession = Depends(get_db),
    _owned: None = Depends(require_project_owner),
) -> list[SectionStatusRead]:
    """Record yes/no answers, then return the whole list again.

    Returning the recomputed list rather than just the answer is what keeps
    the screen honest: answering "no" to 3.2.P.4.6 does not merely record a
    preference, it adds a leaf to the package, and the caller should see
    that happen rather than infer it.
    """
    project = await _get_project_or_404(project_id, db)

    # Only numbers the region profile actually declares conditional are
    # accepted. Anything else is silently dropped rather than stored: an
    # answer to a question nobody asked would sit in the column forever,
    # invisible, and could start meaning something the day that number
    # became conditional in config.
    conditional = {
        number
        for number, resolved in resolve_applicability(project).items()
        if resolved.section.status is Applicability.CONDITIONAL
    }

    answers = dict(project.condition_answers or {})
    for number, answer in payload.answers.items():
        if number not in conditional:
            continue
        if answer is None:
            answers.pop(number, None)
        else:
            answers[number] = answer
    project.condition_answers = answers
    # A JSON column mutated in place is invisible to SQLAlchemy's change
    # detection -- it compares by identity, and a dict that was edited is
    # still the same dict. Reassigning above is usually enough; flagging it
    # explicitly means this stays correct if someone later edits in place.
    flag_modified(project, "condition_answers")

    await db.commit()
    project = await _get_project_or_404(project_id, db)
    return _section_statuses(project)
