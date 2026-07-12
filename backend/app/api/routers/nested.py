"""Instantiates the six Product-child routers from the factory in
product_children.py — one line per resource."""

from __future__ import annotations

from app.api.routers.product_children import build_child_router
from app.models import (
    ActiveIngredient,
    BatchFormulaLine,
    ClinicalEntry,
    Excipient,
    Manufacturer,
    Packaging,
    StabilityStudy,
)
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
from app.schemas.stability import StabilityStudyCreate, StabilityStudyRead, StabilityStudyUpdate

NESTED_ROUTERS = [
    build_child_router(
        resource="manufacturers",
        model=Manufacturer,
        create_schema=ManufacturerCreate,
        update_schema=ManufacturerUpdate,
        read_schema=ManufacturerRead,
    ),
    build_child_router(
        resource="apis",
        model=ActiveIngredient,
        create_schema=ActiveIngredientCreate,
        update_schema=ActiveIngredientUpdate,
        read_schema=ActiveIngredientRead,
    ),
    build_child_router(
        resource="excipients",
        model=Excipient,
        create_schema=ExcipientCreate,
        update_schema=ExcipientUpdate,
        read_schema=ExcipientRead,
    ),
    build_child_router(
        resource="packaging",
        model=Packaging,
        create_schema=PackagingCreate,
        update_schema=PackagingUpdate,
        read_schema=PackagingRead,
    ),
    build_child_router(
        resource="stability",
        model=StabilityStudy,
        create_schema=StabilityStudyCreate,
        update_schema=StabilityStudyUpdate,
        read_schema=StabilityStudyRead,
    ),
    build_child_router(
        resource="clinical",
        model=ClinicalEntry,
        create_schema=ClinicalEntryCreate,
        update_schema=ClinicalEntryUpdate,
        read_schema=ClinicalEntryRead,
    ),
    build_child_router(
        resource="batch-formula",
        model=BatchFormulaLine,
        create_schema=BatchFormulaLineCreate,
        update_schema=BatchFormulaLineUpdate,
        read_schema=BatchFormulaLineRead,
    ),
]
