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
    ClinicalKind,
    CompendialStatus,
    DosageForm,
    ExcipientFunction,
    GMPStatus,
    LegalStatus,
    ManufacturerRole,
    PackagingComponent,
    Region,
    RegistrationType,
    StabilityStudyType,
)
from app.models.product import Product
from app.models.manufacturer import Manufacturer
from app.models.active_ingredient import ActiveIngredient
from app.models.excipient import Excipient
from app.models.packaging import Packaging
from app.models.stability import StabilityStudy
from app.models.clinical import ClinicalEntry
from app.models.batch_formula import BatchFormulaLine
from app.models.project import Project, Section
from app.models.sequence import Sequence
from app.models.user import User

__all__ = [
    "Base",
    # enums
    "ClinicalKind",
    "CompendialStatus",
    "DosageForm",
    "ExcipientFunction",
    "GMPStatus",
    "LegalStatus",
    "ManufacturerRole",
    "PackagingComponent",
    "Region",
    "RegistrationType",
    "StabilityStudyType",
    # entities
    "Product",
    "Manufacturer",
    "ActiveIngredient",
    "Excipient",
    "Packaging",
    "StabilityStudy",
    "ClinicalEntry",
    "BatchFormulaLine",
    "Project",
    "Section",
    "Sequence",
    "User",
]
