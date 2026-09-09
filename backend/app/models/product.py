"""Product: the canonical drug-product record (AGENTS.md §6).

This is master data — it is deliberately NOT owned by a single Project.
The same product can be filed as several Projects over time (a NAFDAC
renewal today, an FDA submission next year); Project.product_id points
here, not the other way round. See build-log.md for why this differs
from the original LAMOX vertical slice, which nested Product 1:1 inside
Project.

WHY owner_id lives here and not on Project: Product is the root of
everything a user can touch — every Project points at a Product, and
every child resource (manufacturers, excipients, specs, ...) hangs off
Product or off an ActiveIngredient that itself hangs off Product. One
owner column here, checked once, covers the whole tree instead of a
column (and a check) repeated on every table.

WHY strength is NOT a column here (it moved to ActiveIngredient): a
fixed-dose combination product -- Ampiclox (ampicillin + cloxacillin),
artemether-lumefantrine -- doesn't have ONE strength, it has one per
active ingredient. A single `strength_value`/`strength_unit` pair on
Product had no honest place to put a second value, which silently made
every combination product unrepresentable. `strength_display` below
derives a human-readable joined string from whatever APIs actually exist,
so single- and multi-API products render the same way without a
special case.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Integer, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import DosageForm, LegalStatus, RegistrationType

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.batch_formula import BatchFormulaLine
    from app.models.bioequivalence import Biowaiver, BioequivalenceStudy, ReferenceProduct
    from app.models.certificate import Certificate
    from app.models.clinical import ClinicalEntry
    from app.models.batch_analysis import BatchAnalysis
    from app.models.excipient import Excipient
    from app.models.impurity import Impurity
    from app.models.manufacturer import Manufacturer
    from app.models.packaging import Packaging
    from app.models.product_information import ProductInformation
    from app.models.project import Project
    from app.models.specification import SpecificationTest
    from app.models.stability import StabilityStudy
    from app.models.user import User


class Product(Base):
    __tablename__ = "product"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    owner: Mapped["User"] = relationship(back_populates="products")

    brand_name: Mapped[str] = mapped_column(String(120))
    generic_name: Mapped[str] = mapped_column(String(200))

    dosage_form: Mapped[DosageForm | None] = mapped_column(SAEnum(DosageForm), nullable=True)
    atc_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    shelf_life_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_condition: Mapped[str | None] = mapped_column(String(300), nullable=True)
    pack_size: Mapped[str | None] = mapped_column(String(120), nullable=True)  # "10x10 blister"
    route_of_administration: Mapped[str | None] = mapped_column(String(60), nullable=True)

    legal_status: Mapped[LegalStatus | None] = mapped_column(SAEnum(LegalStatus), nullable=True)
    registration_type: Mapped[RegistrationType | None] = mapped_column(
        SAEnum(RegistrationType), nullable=True
    )
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # ---- P22: what the APPLICATION claims about its comparator ----------
    #
    # These two are printed on the registration form (1.2) and in the
    # quality overall summary (2.3) -- they are the filing's claim, in the
    # filing's own words. The comparator a study actually dosed is a
    # `ReferenceProduct` row hanging off the study (app/models/
    # bioequivalence.py), and rule R26 refuses to let the two disagree.
    #
    # WHY they are not one field with the study's row: this is exactly the
    # shape `shelf_life_months` has against the stability data. The claim
    # lives on the product and the evidence lives in the data, because the
    # real filing error -- the dossier names one brand throughout and the
    # CRO dosed another -- has to stay REPRESENTABLE in order to be
    # catchable. Collapse them and R26 becomes a check that a field equals
    # itself.
    reference_product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reference_product_manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # WHY this is on the product and not in the rule: the acceptance window
    # for a narrow-therapeutic-index drug is tighter (90.00-111.11 % rather
    # than 80.00-125.00 %), and which drugs those are is a property of the
    # MOLECULE -- warfarin, digoxin, levothyroxine, lithium, phenytoin --
    # not of the region. The region owns the two windows (config); the
    # product owns which of them applies to it. Rule R25 asks both.
    narrow_therapeutic_index: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )

    # ---- children (Product has many of each — AGENTS.md §6) --------------
    manufacturers: Mapped[list["Manufacturer"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    apis: Mapped[list["ActiveIngredient"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    excipients: Mapped[list["Excipient"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    packaging: Mapped[list["Packaging"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    # P21: the FINISHED PRODUCT's stability studies only (3.2.P.8). A
    # study of a drug substance (3.2.S.7) now hangs off the active
    # ingredient instead -- see app/models/stability.py. That split is why
    # R05 can read this collection and mean "the studies that support THIS
    # product's shelf life" without filtering.
    stability: Mapped[list["StabilityStudy"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    clinical: Mapped[list["ClinicalEntry"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    # P22: the structured bioequivalence evidence that replaces the
    # free-text ClinicalEntry row for the one kind of clinical entry a
    # multisource filing actually turns on. `clinical` keeps the others --
    # literature and other clinical studies still belong there.
    bioequivalence_studies: Mapped[list["BioequivalenceStudy"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="BioequivalenceStudy.study_identifier",
    )
    reference_products: Mapped[list["ReferenceProduct"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ReferenceProduct.name",
    )
    biowaivers: Mapped[list["Biowaiver"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="Biowaiver.strength",
    )
    batch_formula: Mapped[list["BatchFormulaLine"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    # P20: the FINISHED PRODUCT's own specification (3.2.P.5.1), its
    # released batches (3.2.P.5.4) and its impurity profile (3.2.P.5.5).
    # There is exactly one finished product, so unlike 3.2.S.4.1 and
    # 3.2.P.4.1 these sections do not repeat.
    specification: Mapped[list["SpecificationTest"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="SpecificationTest.sort_order",
    )
    batch_analyses: Mapped[list["BatchAnalysis"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="BatchAnalysis.batch_number",
    )
    impurities: Mapped[list["Impurity"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="Impurity.name",
    )
    # P23: the SmPC / label / leaflet content, and the only 1:1 child
    # Product has. `uselist=False` is what makes it a single row rather
    # than a collection of one -- see app/models/product_information.py
    # for why three documents read one row.
    product_information: Mapped["ProductInformation | None"] = relationship(
        back_populates="product", cascade="all, delete-orphan", uselist=False
    )

    # ---- reverse side of Project -> Product (many Projects per Product) --
    projects: Mapped[list["Project"]] = relationship(back_populates="product")

    def __init__(self, **kwargs) -> None:
        """Start P22's collections LOADED and empty.

        Exactly the trap `Project.__init__` documents for `documents`, met
        again from a new direction and worth naming precisely: rule R06
        reads `product.biowaivers`, and on a Product that was BUILT in
        Python and then committed, that collection has never been loaded --
        so the attribute access goes to the database. Under the async
        engine, IO from a plain attribute access does not merely block, it
        raises MissingGreenlet, deep inside a synchronous rule and nowhere
        near a query.

        Every other collection here escapes it only by accident: the seeds
        happen to append to all of them, and appending marks a collection
        loaded. `biowaivers` is the first one a complete filing legitimately
        leaves empty -- a filing that ran an in vivo study claims no
        biowaiver -- which is why it is the first to fail.

        (Objects loaded from a query are unaffected: SQLAlchemy does not
        call `__init__` when it materialises a row, and app/api/loading.py
        is what eager-loads them there.)
        """
        for collection in ("bioequivalence_studies", "reference_products", "biowaivers"):
            kwargs.setdefault(collection, [])
        # P23: the same trap, met by a SCALAR relationship for the first
        # time. `product_information` is 1:1 and legitimately absent on a
        # product whose SmPC has not been entered yet, and rules R28-R33
        # all read it -- so on a Product built in Python and committed,
        # the attribute access would go to the database and raise
        # MissingGreenlet inside a synchronous rule. `None` here is the
        # scalar equivalent of the empty lists above: the relationship
        # counts as loaded, and "not entered yet" answers without IO.
        kwargs.setdefault("product_information", None)
        super().__init__(**kwargs)

    @property
    def strength_display(self) -> str:
        """Human-readable strength(s), one "name value unit" per active
        ingredient that has a strength on file, joined with " + " for
        combination products (e.g. "Ampicillin 250 mg + Cloxacillin 250
        mg"). A single-API product just renders as one term -- there is no
        special case for "one active" vs "several"."""
        parts = []
        for api in self.apis:
            if api.strength_value is None:
                continue
            value = f"{float(api.strength_value):g}"
            unit = api.strength_unit or ""
            parts.append(f"{api.inn_name} {value} {unit}".strip())
        return " + ".join(parts)
