"""External validator adapter (P10) -- the 5th repetition of this
project's provider-abstraction shape (LLM client, embedding client,
storage client, `BackboneBuilder`, now this): one interface, a config-
selected implementation, callers never know which one they got.

WHY this exists with only a null implementation: there is no real
agency-recognized validator (an eValidator-class tool) installable in this
environment. Building the seam now means a real adapter can be dropped in
later -- exactly like a real deployment would -- by writing a new
`ExternalValidator` and flipping `ectd_external_validator_provider`,
without touching `app.ectd.report` or anything upstream of it.

WHY the null result is a real `Finding`, not silence: AGENTS.md's own
"never claim gateway-readiness from internal checks alone" rule has to be
something a REPORT SAYS, not just something a docstring promises --
otherwise a caller who never reads this module's comments would have no
way to know the external layer didn't actually run.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings
from app.validation.engine import Finding, Severity

SOURCE = "external-validator"


class ExternalValidator(ABC):
    @abstractmethod
    def validate(self, sequence_zip_bytes: bytes) -> list[Finding]: ...


class NullExternalValidator(ExternalValidator):
    """No real validator wired up -- says so, plainly, as an ADVISORY
    finding (never ERROR: absence of a check is not itself a defect)."""

    def validate(self, sequence_zip_bytes: bytes) -> list[Finding]:
        return [
            Finding(
                rule_id="EXT00",
                severity=Severity.ADVISORY,
                category="external-validator",
                message=(
                    "No agency-recognized external validator is configured in this "
                    "environment -- this report reflects internal checks only. Run an "
                    "agency-recognized validator (e.g. an eValidator-class tool) before "
                    "submission."
                ),
                source=SOURCE,
            )
        ]


@lru_cache
def get_external_validator() -> ExternalValidator:
    settings = get_settings()
    if settings.ectd_external_validator_provider == "null":
        return NullExternalValidator()
    raise NotImplementedError(
        f"No ExternalValidator implementation for "
        f"ectd_external_validator_provider={settings.ectd_external_validator_provider!r}"
    )
