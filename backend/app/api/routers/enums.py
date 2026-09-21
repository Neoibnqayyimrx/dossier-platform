"""Controlled vocabularies, served to the frontend (P11).

WHY this endpoint exists rather than the UI hard-coding the same lists:
these enums ARE the regulatory control (see app/models/enums.py -- a
Postgres ENUM physically cannot store a value that isn't on the approved
list). A second hand-maintained copy in TypeScript is precisely how the
approved list and the offered list drift apart, and "the UI let me pick a
dosage form the database rejects" is the *good* failure mode -- the bad
one is the UI quietly offering a stale vocabulary that a regulator later
queries. Adding a dosage form stays a one-line change to enums.py.

WHY value/label pairs rather than bare strings: the enum MEMBER name
(e.g. TABLET_ENTERIC_COATED) is what code and the DB speak, while
`.value` ("enteric-coated tablet") is what a human reads. The API sends
`.value` for both, since that is what every Create schema accepts -- but
the shape leaves room for a display name to diverge later without
changing the contract.
"""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter

from app.models.enums import (
    CertificateType,
    ClinicalKind,
    CompendialStatus,
    DeclarationType,
    DosageForm,
    ExcipientFunction,
    ExcipientOrigin,
    FDAApplicationType,
    GMPStatus,
    LegalStatus,
    ManufacturerRole,
    PackagingComponent,
    PackagingRole,
    Region,
    AdverseEventFrequency,
    RegistrationType,
    StabilityStudyType,
    SubmissionType,
)

router = APIRouter(prefix="/enums", tags=["enums"])

# The vocabularies the product wizard and project forms need. Deliberately
# NOT every enum in the module -- KBSource/NarrativeStatus are internal
# machinery, never a user's choice.
_VOCABULARIES: dict[str, type[Enum]] = {
    "region": Region,
    "submission_type": SubmissionType,
    "registration_type": RegistrationType,
    "dosage_form": DosageForm,
    "legal_status": LegalStatus,
    "compendial_status": CompendialStatus,
    "excipient_function": ExcipientFunction,
    "excipient_origin": ExcipientOrigin,
    "manufacturer_role": ManufacturerRole,
    "gmp_status": GMPStatus,
    "packaging_component": PackagingComponent,
    "packaging_role": PackagingRole,
    "stability_study_type": StabilityStudyType,
    "clinical_kind": ClinicalKind,
    "certificate_type": CertificateType,
    "declaration_type": DeclarationType,
    # P23: the CIOMS frequency bands for SmPC 4.8. A controlled vocabulary
    # rather than a text field because both the SmPC and the leaflet print
    # them in band order, and an order needs a defined set.
    "adverse_event_frequency": AdverseEventFrequency,
    # gap Phase 4b: which FDA application a project's number belongs to.
    "fda_application_type": FDAApplicationType,
}


@router.get("")
async def list_enums() -> dict[str, list[dict[str, str]]]:
    return {
        name: [{"value": member.value, "label": member.value} for member in enum_cls]
        for name, enum_cls in _VOCABULARIES.items()
    }
