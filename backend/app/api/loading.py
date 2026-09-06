"""Eager-load options for read endpoints.

WHY this file exists: SQLAlchemy's async engine cannot lazy-load a
relationship after the fact (it needs a greenlet context that only exists
inside the query itself) — touching an un-loaded relationship from a
`Read` schema's serialization raises `MissingGreenlet`. Every relationship a
`*Read` schema nests must therefore be `selectinload`ed up front, in the
query that fetches the row. Centralized here so every router loads the same
shape the schema expects.
"""

from __future__ import annotations

from sqlalchemy.orm import selectinload

from app.models import (
    ActiveIngredient,
    BatchAnalysis,
    BatchAnalysisResult,
    BatchFormulaLine,
    Excipient,
    Product,
    Project,
)

# Every child collection ProductRead nests (app/schemas/product.py).
PRODUCT_CHILD_OPTIONS = (
    selectinload(Product.manufacturers),
    selectinload(Product.apis).selectinload(ActiveIngredient.specification),
    selectinload(Product.excipients),
    selectinload(Product.packaging),
    selectinload(Product.stability),
    selectinload(Product.clinical),
    selectinload(Product.batch_formula),
)

# ProjectRead nests product (with all its children) + sequences.
PROJECT_CHILD_OPTIONS = (
    selectinload(Project.product).selectinload(Product.manufacturers),
    selectinload(Project.product)
    .selectinload(Product.apis)
    .selectinload(ActiveIngredient.specification),
    selectinload(Project.product).selectinload(Product.excipients),
    selectinload(Project.product).selectinload(Product.packaging),
    selectinload(Project.product).selectinload(Product.stability),
    selectinload(Project.product).selectinload(Product.clinical),
    selectinload(Project.product).selectinload(Product.batch_formula),
    selectinload(Project.sequences),
    # P15a: ProjectRead nests these two, so every project read has to load
    # them -- not just the readiness path that already did below.
    selectinload(Project.applicant),
    selectinload(Project.declarations),
)

# P13: R07 reads each API's specification ROWS now (not a free-text field),
# so that collection has to be loaded here too or the rule raises
# MissingGreenlet -- the same trap the docstring above describes.
# P06's run_all() walks the full project graph (rules read manufacturers,
# apis + each API's manufacturer, batch_formula + each line's active
# ingredient, certificates, and the project's sections) -- every one of
# those relationships must be eager-loaded here, or a rule touching an
# un-loaded one raises MissingGreenlet inside the (sync) rule function.
READINESS_LOAD_OPTIONS = PROJECT_CHILD_OPTIONS + (
    selectinload(Project.product)
    .selectinload(Product.apis)
    .selectinload(ActiveIngredient.manufacturer),
    selectinload(Project.product)
    .selectinload(Product.batch_formula)
    .selectinload(BatchFormulaLine.active_ingredient),
    selectinload(Project.product).selectinload(Product.certificates),
    selectinload(Project.sections),
    # P20. R22 walks batch -> results -> the specification test each result
    # answers, and R11 now reads impurity limits; the P20 sections render
    # from the excipient and drug-product specifications. Every one of
    # those is a relationship that did not exist when this list was last
    # written, and the failure mode is the one this module's docstring
    # describes -- MissingGreenlet, raised deep inside a synchronous rule,
    # nowhere near the query that forgot to load it.
    #
    # The result -> specification_test hop is the load-bearing one: it is
    # how R22 reaches the limit WITHOUT a copy of it, which is the whole
    # design. It is also two levels down, and `selectinload` chains have to
    # spell out every level.
    selectinload(Project.product)
    .selectinload(Product.apis)
    .selectinload(ActiveIngredient.batch_analyses)
    .selectinload(BatchAnalysis.results)
    .selectinload(BatchAnalysisResult.specification_test),
    selectinload(Project.product)
    .selectinload(Product.apis)
    .selectinload(ActiveIngredient.batch_analyses)
    .selectinload(BatchAnalysis.manufacturer),
    selectinload(Project.product)
    .selectinload(Product.apis)
    .selectinload(ActiveIngredient.impurities),
    selectinload(Project.product)
    .selectinload(Product.excipients)
    .selectinload(Excipient.specification),
    selectinload(Project.product).selectinload(Product.specification),
    selectinload(Project.product)
    .selectinload(Product.batch_analyses)
    .selectinload(BatchAnalysis.results)
    .selectinload(BatchAnalysisResult.specification_test),
    selectinload(Project.product)
    .selectinload(Product.batch_analyses)
    .selectinload(BatchAnalysis.manufacturer),
    selectinload(Project.product).selectinload(Product.impurities),
)
