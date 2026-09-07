"""Domain models for a dossier project (AGENTS.md §6).

These tables are the SINGLE SOURCE OF TRUTH. Every generated document reads
from here; the LLM never re-types a value that lives in this file. A
regulator cross-checks these values across modules, so the validation
engine (app/validation) checks them here too.

Each entity lives in its own module; this file just re-exports everything
so callers can keep writing `from app.models import Product, ...`.
"""

from __future__ import annotations

from app.models.base import Base
from app.models.enums import (
    CertificateType,
    ClinicalKind,
    CompendialStatus,
    DeclarationType,
    DECLARATIONS_REQUIRING_NOTARIZATION,
    TSE_RELEVANT_ORIGINS,
    DosageForm,
    ExcipientFunction,
    ExcipientOrigin,
    GMPStatus,
    ImpurityType,
    KBLicense,
    KBSource,
    LegalStatus,
    ManufacturerRole,
    NarrativeStatus,
    PackagingComponent,
    PackagingRole,
    Region,
    RegistrationType,
    SpecificationOwnerKind,
    StabilityStudyType,
    SubmissionType,
)
from app.models.product import Product
from app.models.manufacturer import Manufacturer
from app.models.active_ingredient import ActiveIngredient
from app.models.excipient import Excipient
from app.models.packaging import Packaging
from app.models.stability import StabilityResult, StabilityStudy
from app.models.clinical import ClinicalEntry
from app.models.batch_formula import BatchFormulaLine
from app.models.specification import SpecificationTest
from app.models.batch_analysis import BatchAnalysis, BatchAnalysisResult
from app.models.impurity import Impurity
from app.models.certificate import Certificate
from app.models.applicant import Applicant
from app.models.declaration import Declaration
from app.models.project import Project, Section
from app.models.section_document import SectionDocument
from app.models.sequence import Sequence
from app.models.sequence_leaf import SequenceLeaf
from app.models.user import User
from app.models.kb import KBChunk, KBDocument
from app.models.narrative import NarrativeGeneration
from app.models.validation_override import ValidationOverride

__all__ = [
    "Base",
    "SpecificationTest",
    "SectionDocument",
    # enums
    "CertificateType",
    "ClinicalKind",
    "CompendialStatus",
    "DeclarationType",
    "DECLARATIONS_REQUIRING_NOTARIZATION",
    "TSE_RELEVANT_ORIGINS",
    "DosageForm",
    "ExcipientFunction",
    "ExcipientOrigin",
    "GMPStatus",
    "ImpurityType",
    "KBLicense",
    "KBSource",
    "LegalStatus",
    "ManufacturerRole",
    "NarrativeStatus",
    "PackagingComponent",
    "PackagingRole",
    "Region",
    "RegistrationType",
    "SpecificationOwnerKind",
    "StabilityStudyType",
    "SubmissionType",
    # entities
    "Product",
    "Manufacturer",
    "ActiveIngredient",
    "Excipient",
    "Packaging",
    "StabilityStudy",
    "StabilityResult",
    "ClinicalEntry",
    "BatchFormulaLine",
    "BatchAnalysis",
    "BatchAnalysisResult",
    "Impurity",
    "Certificate",
    "Applicant",
    "Declaration",
    "Project",
    "Section",
    "Sequence",
    "SequenceLeaf",
    "User",
    "KBDocument",
    "KBChunk",
    "NarrativeGeneration",
    "ValidationOverride",
]
