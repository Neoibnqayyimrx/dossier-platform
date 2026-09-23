"""The SmPC / label / leaflet content, and the three-way comparison (P23).

Hand-written rather than built from `product_children.build_child_router`,
and the reason is structural rather than stylistic: this is the only 1:1
child Product has. The factory's shape is a COLLECTION -- POST to add,
DELETE by id, list them all -- and "add a second SmPC" is not an operation
that means anything. `PUT` create-or-replace is the honest verb for a
resource of which there is exactly one.

## Two scopes, on purpose

Editing is PRODUCT-scoped (`/products/{id}/product-information`): the
clinical particulars are facts about the medicine, and they survive being
filed again in another region next year -- the same reasoning that put
`Product` above `Project` in the first place.

The comparison is PROJECT-scoped
(`/projects/{id}/product-information/comparison`): it compares what three
DOCUMENTS print, and a document belongs to a filing. It needs the project
for the same reason every other rendered section does -- the marketing
authorisation holder comes off the applicant, which is a filing fact.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models import (
    Product,
    ProductInformation,
    Project,
    StabilityResult,
    StabilityStudy,
    User,
)
from app.schemas.product_information import (
    ComparisonRow,
    DerivedValue,
    DocumentValue,
    ProductInformationRead,
    ProductInformationWrite,
    ThreeWayComparison,
)
from app.templating.context import build_context
from app.templating.product_information import shared_values
from app.templating.registry import get_section

router = APIRouter(tags=["product-information"])

# The three leaves, and what to call each on the comparison screen. The
# titles come from the registry rather than being retyped, so a renamed
# section renames itself here too.
_DOCUMENTS = ("1.3.1", "1.3.2", "1.3.3")


async def _get_product_or_404(product_id: uuid.UUID, user: User, db: AsyncSession) -> Product:
    """The product, if this user owns it.

    404, never 403 -- someone else's product must look exactly like one
    that does not exist. The call every other router here makes.
    """
    product = await db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.organization_id == user.organization_id)
        .options(
            selectinload(Product.product_information),
            selectinload(Product.apis),
            selectinload(Product.excipients),
            selectinload(Product.packaging),
            # THREE levels, and each one was found by being bitten:
            # `shared_values` -> shelf-life statement ->
            # StabilityStudy.supported_months -> each RESULT ->
            # result.fails() -> meets_criterion -> that result's
            # SPECIFICATION TEST (it needs the acceptance criterion to
            # decide). Loading only `Product.stability` left two lazy hops,
            # so a product with real stability data raised MissingGreenlet
            # here -- a 500 on GET and PUT alike.
            #
            # WHY no test caught it: it fires only once a product has
            # stability RESULTS, and the tests here built products without
            # them. The endpoint worked perfectly until a filing had data.
            selectinload(Product.stability)
            .selectinload(StabilityStudy.results)
            .selectinload(StabilityResult.specification_test),
        )
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


def _read(product: Product) -> ProductInformationRead:
    """Serialise the row plus the derived block.

    WHY the derived values are attached here rather than being properties
    on the model: they are computed from the product's OTHER children
    (stability, packaging, actives), which the model layer would have to
    walk lazily -- and a lazily-walked relationship on the async engine is
    the MissingGreenlet trap this codebase has now met four times. The
    route has already eager-loaded exactly what `shared_values` reads.
    """
    information = product.product_information
    if information is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No product information has been entered for this product yet.",
        )
    payload = ProductInformationRead.model_validate(information)
    payload.derived = [DerivedValue(**value.__dict__) for value in shared_values(product)]
    return payload


@router.get("/products/{product_id}/product-information", response_model=ProductInformationRead)
async def get_product_information(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product = await _get_product_or_404(product_id, user, db)
    return _read(product)


@router.put("/products/{product_id}/product-information", response_model=ProductInformationRead)
async def upsert_product_information(
    product_id: uuid.UUID,
    payload: ProductInformationWrite,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create or replace the product information.

    REPLACE, not merge, for the same reason the bioequivalence results are
    replaced as a set: the SmPC sections on the filer's screen ARE the
    SmPC, so a contraindication they deleted has to be gone from the SmPC
    AND from the leaflet, not linger because the payload no longer
    mentioned it.

    A request carrying a derived field (`shelf_life_months`, say) never
    reaches this function: `ProductInformationWrite` forbids extra keys, so
    FastAPI answers 422 naming the offending field. That refusal is the
    point -- see the schema module's docstring.
    """
    product = await _get_product_or_404(product_id, user, db)
    information = product.product_information
    if information is None:
        information = ProductInformation(product_id=product.id)
        db.add(information)
        product.product_information = information

    values = payload.model_dump()
    # The two structured lists arrive as Pydantic models; the JSON column
    # needs plain dicts. `mode="json"` on the dump would also serialise the
    # enum, but it would serialise the datetimes elsewhere in this codebase
    # differently from every other writer -- so the conversion is explicit
    # and local to the one field that needs it.
    values["undesirable_effects"] = [
        {"effect": effect.effect, "frequency": effect.frequency.value}
        for effect in payload.undesirable_effects
    ]
    for name, value in values.items():
        setattr(information, name, value)

    await db.commit()
    # WHY the refresh, when nothing else in this codebase needs one after a
    # commit: the session runs with `expire_on_commit=False`, so an UPDATE
    # normally leaves every attribute readable. `Base.updated_at` is the
    # exception -- it carries `onupdate=func.now()`, so SQLAlchemy marks it
    # stale after an UPDATE regardless, and the next read of it is IO. On
    # the async engine that read happens inside Pydantic's serialisation,
    # where it raises MissingGreenlet rather than blocking.
    #
    # It announced itself as a failure on the SECOND PUT only, which is
    # what makes it worth naming: the first PUT INSERTs, and an insert's
    # server defaults are fetched with the row, so create-then-read looked
    # perfectly healthy while update-then-read did not.
    await db.refresh(information)
    return _read(product)


async def _get_project_or_404(project_id: uuid.UUID, user: User, db: AsyncSession) -> Project:
    project = await db.scalar(
        select(Project)
        .join(Product, Product.id == Project.product_id)
        .where(Project.id == project_id, Product.organization_id == user.organization_id)
        .options(
            selectinload(Project.applicant),
            selectinload(Project.product).selectinload(Product.product_information),
            selectinload(Project.product).selectinload(Product.apis),
            selectinload(Project.product).selectinload(Product.excipients),
            selectinload(Project.product).selectinload(Product.packaging),
            selectinload(Project.product).selectinload(Product.manufacturers),
            selectinload(Project.product).selectinload(Product.stability),
        )
    )
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


@router.get(
    "/projects/{project_id}/product-information/comparison",
    response_model=ThreeWayComparison,
)
async def compare_product_information(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The SmPC, the label and the leaflet, side by side on every shared field.

    WHY this asks the three CONTEXT BUILDERS rather than calling
    `shared_values` once and reporting it three times: reporting one value
    three times would be a screen that always agrees because it only ever
    looked once. This renders what each document will actually print, which
    is the same thing rule R31 does -- so the screen and the export gate
    cannot come to different conclusions.

    A row where the three differ is a genuine finding. Today none can, and
    that is the demonstration: the screen shows a defect class that the
    filing is structurally unable to contain.
    """
    project = await _get_project_or_404(project_id, user, db)
    contexts = {number: build_context(number, project) for number in _DOCUMENTS}
    shared = {number: context.get("shared", {}) for number, context in contexts.items()}

    rows: list[ComparisonRow] = []
    for value in shared_values(project.product):
        printed = [
            DocumentValue(
                section=number,
                document=get_section(number).title,
                value=shared[number].get(value.field, ""),
            )
            for number in _DOCUMENTS
            # A document that does not print this field at all is left out
            # rather than shown as blank: the leaflet has no "legal status
            # of supply" line, and rendering an empty cell there would read
            # as a divergence when it is a difference in scope.
            if value.field in shared[number]
        ]
        rows.append(
            ComparisonRow(
                field=value.field,
                label=value.label,
                smpc_section=value.smpc_section,
                source=value.source,
                values=printed,
                agrees=len({item.value for item in printed}) <= 1,
            )
        )

    return ThreeWayComparison(rows=rows, divergences=sum(1 for row in rows if not row.agrees))
