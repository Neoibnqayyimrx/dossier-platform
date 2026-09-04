"""Instantiates every child-collection router from the factory in
product_children.py — one entry per resource.

Most parents are Product. Two are not: a specification belongs to one
active ingredient, and a declaration belongs to one project. Both reach
their owner through `owner_via`, which names the relationship to walk to
the Product that carries owner_id.
"""

from __future__ import annotations

from app.api.routers.product_children import build_child_router
from app.models import (
    ActiveIngredient,
    BatchFormulaLine,
    Certificate,
    ClinicalEntry,
    Declaration,
    Excipient,
    Manufacturer,
    Packaging,
    Project,
    SpecificationTest,
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
from app.schemas.certificate import CertificateCreate, CertificateRead, CertificateUpdate
from app.schemas.clinical import ClinicalEntryCreate, ClinicalEntryRead, ClinicalEntryUpdate
from app.schemas.declaration import DeclarationCreate, DeclarationRead, DeclarationUpdate
from app.schemas.excipient import ExcipientCreate, ExcipientRead, ExcipientUpdate
from app.schemas.manufacturer import ManufacturerCreate, ManufacturerRead, ManufacturerUpdate
from app.schemas.packaging import PackagingCreate, PackagingRead, PackagingUpdate
from app.schemas.specification import (
    SpecificationTestCreate,
    SpecificationTestRead,
    SpecificationTestUpdate,
)
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
        nested_collections=("specification",),
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
    # P15a: a Certificate is proof about the PRODUCT (a CPP attests to the
    # medicine and survives re-filing), so it is product-scoped like any
    # other child here -- see app.models.certificate's WHY.
    build_child_router(
        resource="certificates",
        model=Certificate,
        create_schema=CertificateCreate,
        update_schema=CertificateUpdate,
        read_schema=CertificateRead,
    ),
    # The one child whose parent is NOT a Product: a drug-substance
    # specification belongs to a single active ingredient, because a
    # fixed-dose combination has one specification per active (3.2.S is
    # repeated per drug substance).
    build_child_router(
        resource="specification",
        model=SpecificationTest,
        create_schema=SpecificationTestCreate,
        update_schema=SpecificationTestUpdate,
        read_schema=SpecificationTestRead,
        parent_model=ActiveIngredient,
        parent_segment="apis",
        parent_fk="active_ingredient_id",
        order_by="sort_order",
        owner_via="product",
    ),
    # P15a: the other non-Product parent. A Declaration (Power of Attorney,
    # Declaration of Authenticity) names a representative for THIS filing,
    # so it belongs to the Project -- next year's renewal may appoint
    # someone else. Project -> Product is one hop, so the same owner_via
    # the specification router uses covers it unchanged.
    build_child_router(
        resource="declarations",
        model=Declaration,
        create_schema=DeclarationCreate,
        update_schema=DeclarationUpdate,
        read_schema=DeclarationRead,
        parent_model=Project,
        parent_segment="projects",
        parent_fk="project_id",
        owner_via="product",
    ),
]
