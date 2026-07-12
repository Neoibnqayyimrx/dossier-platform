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

from app.models import Product, Project

# Every child collection ProductRead nests (app/schemas/product.py).
PRODUCT_CHILD_OPTIONS = (
    selectinload(Product.manufacturers),
    selectinload(Product.apis),
    selectinload(Product.excipients),
    selectinload(Product.packaging),
    selectinload(Product.stability),
    selectinload(Product.clinical),
    selectinload(Product.batch_formula),
)

# ProjectRead nests product (with all its children) + sequences.
PROJECT_CHILD_OPTIONS = (
    selectinload(Project.product).selectinload(Product.manufacturers),
    selectinload(Project.product).selectinload(Product.apis),
    selectinload(Project.product).selectinload(Product.excipients),
    selectinload(Project.product).selectinload(Product.packaging),
    selectinload(Project.product).selectinload(Product.stability),
    selectinload(Project.product).selectinload(Product.clinical),
    selectinload(Project.product).selectinload(Product.batch_formula),
    selectinload(Project.sequences),
)
