"""Consolidated eCTD validation report (P10): merges P06 (data rules),
the mechanical eCTD checks, the external validator, and the AI reviewer
into ONE `Report` -- "merge 4 report types" became "concatenate 4 lists
of `Finding`", thanks to `Finding.source` (see app.validation.engine).
"""

from __future__ import annotations

import io
import uuid
import zipfile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import StorageClient, get_storage_client
from app.ectd.ai_review import SOURCE as AI_SOURCE, review_narratives
from app.ectd.external_validator import ExternalValidator, get_external_validator
from app.ectd.validate import run_mechanical_checks
from app.models.project import Project
from app.models.sequence import Sequence
from app.models.sequence_leaf import SequenceLeaf
from app.validation.engine import Finding, Report, Severity, run_all


class SequenceNotBuiltError(RuntimeError):
    """The sequence being validated (or one a lifecycle reference points
    at) was never built -- distinct from "validation found problems"."""


def _zip_key(project_id: uuid.UUID, sequence_number: str) -> str:
    return f"projects/{project_id}/ectd/{sequence_number}.zip"


def _unzip(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _fetch_sequence_files(
    storage: StorageClient, project_id: uuid.UUID, sequence_number: str
) -> dict[str, bytes] | None:
    # WHY a broad except, not `except KeyError`: "missing" raises
    # differently per storage provider -- InMemoryStorageClient raises
    # KeyError, S3StorageClient raises a boto3-specific ClientError. This
    # helper has to work with either without importing a provider-specific
    # exception type into provider-agnostic code.
    try:
        data = storage.get(_zip_key(project_id, sequence_number))
    except Exception:
        return None
    return _unzip(data)


async def validate_ectd_sequence(
    db: AsyncSession,
    project: Project,
    sequence: Sequence,
    *,
    storage: StorageClient | None = None,
    external_validator: ExternalValidator | None = None,
    run_ai_review: bool = True,
) -> Report:
    storage = storage or get_storage_client()
    external_validator = external_validator or get_external_validator()

    report = Report()
    report.add(*run_all(project).findings)  # P06 -- source defaults to "data-rule"

    files = _fetch_sequence_files(storage, project.id, sequence.number)
    if files is None:
        raise SequenceNotBuiltError(
            f"Sequence {sequence.number} has not been built yet -- nothing to validate"
        )

    prior_numbers = (
        await db.scalars(
            select(Sequence.number).where(
                Sequence.project_id == project.id, Sequence.number < sequence.number
            )
        )
    ).all()
    prior_files: dict[str, dict[str, bytes]] = {}
    for number in prior_numbers:
        bundle = _fetch_sequence_files(storage, project.id, number)
        if bundle is not None:
            prior_files[number] = bundle

    live_section_keys = set(
        (
            await db.scalars(
                select(SequenceLeaf.section_key).where(SequenceLeaf.sequence_id == sequence.id)
            )
        ).all()
    )

    report.add(*run_mechanical_checks(sequence.number, files, prior_files, live_section_keys))
    report.add(*external_validator.validate(storage.get(_zip_key(project.id, sequence.number))))

    if run_ai_review:
        # WHY a broad except that degrades instead of propagating: the AI
        # reviewer is the ADDITIVE layer. A missing API key, a rate limit,
        # or a provider outage must never take down the deterministic
        # report a human actually needs -- "advisory-only" has to mean the
        # layer can't hurt you when it FAILS, not just when it disagrees.
        # The degradation is itself a visible finding, never silence.
        try:
            report.add(*await review_narratives(db, project))
        except Exception as exc:  # noqa: BLE001 -- see WHY above
            report.add(
                Finding(
                    rule_id="AI99",
                    severity=Severity.ADVISORY,
                    category="ai-review",
                    message=f"AI reviewer did not run ({type(exc).__name__}: {exc})",
                    source=AI_SOURCE,
                )
            )

    return report
