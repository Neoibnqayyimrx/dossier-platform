"""Instantiates every child-collection router from the factory in
product_children.py — one entry per resource.

Most parents are Product. Several are not: a declaration belongs to one
project, and a specification belongs to whichever of three things it is a
specification OF. All of them reach their owner through `owner_via`, which
names the relationship to walk to the Product that carries owner_id.

P20 made `specification` the first resource mounted THREE TIMES, under
three different parents, from one model and one pair of schemas. That is
the polymorphic owner paying off at the API layer: the same table is
reachable as `/apis/{id}/specification`, `/products/{id}/specification` and
`/excipients/{id}/specification`, with no second CRUD implementation and no
way for the three to drift apart in what they validate or how they order.

The owner is always taken from the URL PATH, never from the request body
(see app/schemas/specification.py) -- the ownership check the factory runs
is on the parent in the path, so the path is the only place an owner can be
trusted to come from.
"""

from __future__ import annotations

from app.api.routers.product_children import build_child_router
from app.models import (
    ActiveIngredient,
    BatchAnalysis,
    BatchFormulaLine,
    Certificate,
    ClinicalEntry,
    Declaration,
    Excipient,
    Impurity,
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
from app.schemas.batch_analysis import (
    BatchAnalysisCreate,
    BatchAnalysisRead,
    BatchAnalysisUpdate,
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
from app.schemas.impurity import ImpurityCreate, ImpurityRead, ImpurityUpdate
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
    # ---- one specification model, three mount points (P20) -------------
    #
    # 3.2.S.4.1: per drug substance, because a fixed-dose combination has one
    # specification per active -- ampicillin's assay limits are not
    # cloxacillin's.
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
    # 3.2.P.5.1: the finished product's own specification. Product IS the
    # owner here, so no owner_via hop -- the one mount point of the three
    # that needs none.
    build_child_router(
        resource="specification",
        model=SpecificationTest,
        create_schema=SpecificationTestCreate,
        update_schema=SpecificationTestUpdate,
        read_schema=SpecificationTestRead,
        parent_fk="product_id",
        order_by="sort_order",
    ),
    # 3.2.P.4.1: per excipient.
    build_child_router(
        resource="specification",
        model=SpecificationTest,
        create_schema=SpecificationTestCreate,
        update_schema=SpecificationTestUpdate,
        read_schema=SpecificationTestRead,
        parent_model=Excipient,
        parent_segment="excipients",
        parent_fk="excipient_id",
        order_by="sort_order",
        owner_via="product",
    ),
    # ---- batches and impurities, on the same two-owner pattern ----------
    #
    # 3.2.S.4.4 / 3.2.P.5.4. The RESULTS inside a batch are not a factory
    # router: recording one requires checking that the specification test it
    # answers belongs to the same owner as the batch, which is a rule about
    # two parents at once. See app/api/routers/batch_results.py.
    build_child_router(
        resource="batches",
        model=BatchAnalysis,
        create_schema=BatchAnalysisCreate,
        update_schema=BatchAnalysisUpdate,
        read_schema=BatchAnalysisRead,
        parent_model=ActiveIngredient,
        parent_segment="apis",
        parent_fk="active_ingredient_id",
        order_by="batch_number",
        nested_collections=("results",),
        owner_via="product",
    ),
    build_child_router(
        resource="batches",
        model=BatchAnalysis,
        create_schema=BatchAnalysisCreate,
        update_schema=BatchAnalysisUpdate,
        read_schema=BatchAnalysisRead,
        parent_fk="product_id",
        order_by="batch_number",
        nested_collections=("results",),
    ),
    # 3.2.S.3.2 / 3.2.P.5.5.
    build_child_router(
        resource="impurities",
        model=Impurity,
        create_schema=ImpurityCreate,
        update_schema=ImpurityUpdate,
        read_schema=ImpurityRead,
        parent_model=ActiveIngredient,
        parent_segment="apis",
        parent_fk="active_ingredient_id",
        order_by="name",
        owner_via="product",
    ),
    build_child_router(
        resource="impurities",
        model=Impurity,
        create_schema=ImpurityCreate,
        update_schema=ImpurityUpdate,
        read_schema=ImpurityRead,
        parent_fk="product_id",
        order_by="name",
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
