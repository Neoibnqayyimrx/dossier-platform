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
    BioequivalenceStudy,
    Biowaiver,
    Excipient,
    Product,
    Project,
    StabilityResult,
    StabilityStudy,
)

# Every child collection ProductRead nests (app/schemas/product.py).
PRODUCT_CHILD_OPTIONS = (
    selectinload(Product.manufacturers),
    selectinload(Product.apis).selectinload(ActiveIngredient.specification),
    selectinload(Product.excipients),
    selectinload(Product.packaging),
    # P21: StabilityStudyRead nests its RESULTS, and each result derives
    # `meets_criterion` by reading the limit through its specification
    # test -- so this is three levels deep now, not one. A shallow load
    # here raises MissingGreenlet inside Pydantic while serializing a
    # perfectly ordinary GET /products/{id}, which is exactly the failure
    # this module's docstring describes.
    selectinload(Product.stability)
    .selectinload(StabilityStudy.results)
    .selectinload(StabilityResult.specification_test),
    selectinload(Product.clinical),
    # P22. ProductRead nests the bioequivalence studies, and each study
    # nests its confidence intervals -- so this is two levels, and the
    # comparator and the test batch are a third that BioequivalenceStudy's
    # own derived fields do not touch but every renderer does. The lesson
    # P21's log recorded and P20's before it: adding a nested field to a
    # *Read schema is an eager-loading change.
    selectinload(Product.bioequivalence_studies).selectinload(BioequivalenceStudy.results),
    selectinload(Product.reference_products),
    selectinload(Product.biowaivers),
    selectinload(Product.batch_formula),
    # P23: the SmPC content. A 1:1 relationship is eager-loaded exactly like
    # a collection -- `uselist=False` changes what comes back, not whether
    # touching it un-loaded raises MissingGreenlet.
    selectinload(Product.product_information),
)

# ProjectRead nests product (with all its children) + sequences.
PROJECT_CHILD_OPTIONS = (
    selectinload(Project.product).selectinload(Product.manufacturers),
    selectinload(Project.product)
    .selectinload(Product.apis)
    .selectinload(ActiveIngredient.specification),
    selectinload(Project.product).selectinload(Product.excipients),
    selectinload(Project.product).selectinload(Product.packaging),
    selectinload(Project.product)
    .selectinload(Product.stability)
    .selectinload(StabilityStudy.results)
    .selectinload(StabilityResult.specification_test),
    selectinload(Project.product).selectinload(Product.clinical),
    # P22, the same three collections through the project.
    selectinload(Project.product)
    .selectinload(Product.bioequivalence_studies)
    .selectinload(BioequivalenceStudy.results),
    selectinload(Project.product).selectinload(Product.reference_products),
    selectinload(Project.product).selectinload(Product.biowaivers),
    selectinload(Project.product).selectinload(Product.batch_formula),
    selectinload(Project.product).selectinload(Product.product_information),
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
    # P21. R05, R23 and R24 walk stability -> results -> the specification
    # test each result answers, on BOTH owners -- the finished product
    # (3.2.P.8) and each drug substance (3.2.S.7). The result ->
    # specification_test hop is the load-bearing one again: it is how R23
    # reaches the limit without a copy of it. Three levels down, and
    # selectinload chains have to spell out every level.
    #
    # The study's batch and pack are loaded too, because a finding names
    # them: "batch AMP/24/0101, blister" is what makes an R23 finding point
    # at a page of the stability report rather than at a condition.
    selectinload(Project.product)
    .selectinload(Product.stability)
    .selectinload(StabilityStudy.results)
    .selectinload(StabilityResult.specification_test),
    selectinload(Project.product)
    .selectinload(Product.stability)
    .selectinload(StabilityStudy.batch_analysis),
    selectinload(Project.product)
    .selectinload(Product.stability)
    .selectinload(StabilityStudy.packaging),
    selectinload(Project.product)
    .selectinload(Product.apis)
    .selectinload(ActiveIngredient.stability)
    .selectinload(StabilityStudy.results)
    .selectinload(StabilityResult.specification_test),
    selectinload(Project.product)
    .selectinload(Product.apis)
    .selectinload(ActiveIngredient.stability)
    .selectinload(StabilityStudy.batch_analysis),
    selectinload(Project.product)
    .selectinload(Product.apis)
    .selectinload(ActiveIngredient.stability)
    .selectinload(StabilityStudy.packaging),
    # P22. R25 walks study -> results, R26 walks study -> reference
    # product, and R27 walks study -> test batch; the BTI form (1.4.1) and
    # the tabular listing (5.2) walk all three. Every one of those is a
    # relationship that did not exist when this list was last written, and
    # the failure mode is the one this module's docstring describes:
    # MissingGreenlet, raised deep inside a synchronous rule, nowhere near
    # the query that forgot to load it.
    selectinload(Project.product)
    .selectinload(Product.bioequivalence_studies)
    .selectinload(BioequivalenceStudy.reference_product),
    selectinload(Project.product)
    .selectinload(Product.bioequivalence_studies)
    .selectinload(BioequivalenceStudy.test_batch),
    # The biowaiver's supporting study, which 1.2.18 PRINTS by identifier:
    # a request citing a study the dossier does not contain is precisely
    # what the foreign key exists to prevent, and printing it is what makes
    # the link visible to an assessor.
    selectinload(Project.product)
    .selectinload(Product.biowaivers)
    .selectinload(Biowaiver.supporting_study),
)
