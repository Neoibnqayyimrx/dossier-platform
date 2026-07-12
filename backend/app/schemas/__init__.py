"""Pydantic Create/Update/Read schemas mirroring app/models.

`Read` schemas are built with `from_attributes=True` so they can serialize a
SQLAlchemy ORM instance directly (`ProductRead.model_validate(product)`);
`Create`/`Update` schemas are the API's input shapes.
"""

from __future__ import annotations

from app.schemas.active_ingredient import (
    ActiveIngredientCreate,
    ActiveIngredientRead,
    ActiveIngredientUpdate,
)
from app.schemas.batch_formula import (
    BatchFormulaLineCreate,
    BatchFormulaLineRead,
    BatchFormulaLineUpdate,
)
from app.schemas.clinical import ClinicalEntryCreate, ClinicalEntryRead, ClinicalEntryUpdate
from app.schemas.excipient import ExcipientCreate, ExcipientRead, ExcipientUpdate
from app.schemas.manufacturer import ManufacturerCreate, ManufacturerRead, ManufacturerUpdate
from app.schemas.packaging import PackagingCreate, PackagingRead, PackagingUpdate
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.schemas.sequence import SequenceCreate, SequenceRead, SequenceUpdate
from app.schemas.stability import StabilityStudyCreate, StabilityStudyRead, StabilityStudyUpdate
from app.schemas.user import Token, UserCreate, UserRead

__all__ = [
    "ActiveIngredientCreate",
    "ActiveIngredientRead",
    "ActiveIngredientUpdate",
    "BatchFormulaLineCreate",
    "BatchFormulaLineRead",
    "BatchFormulaLineUpdate",
    "ClinicalEntryCreate",
    "ClinicalEntryRead",
    "ClinicalEntryUpdate",
    "ExcipientCreate",
    "ExcipientRead",
    "ExcipientUpdate",
    "ManufacturerCreate",
    "ManufacturerRead",
    "ManufacturerUpdate",
    "PackagingCreate",
    "PackagingRead",
    "PackagingUpdate",
    "ProductCreate",
    "ProductRead",
    "ProductUpdate",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "SequenceCreate",
    "SequenceRead",
    "SequenceUpdate",
    "StabilityStudyCreate",
    "StabilityStudyRead",
    "StabilityStudyUpdate",
    "Token",
    "UserCreate",
    "UserRead",
]
