"""Domain models for a dossier project, reverse-engineered from the LAMOX CTD.

The whole point of these tables: they are the SINGLE SOURCE OF TRUTH. Every
generated document reads from here. The LLM never re-types a value that lives
in this file. A regulator cross-checks these values across modules, so the
validation engine (app/validation) checks them here too.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import String, Integer, Numeric, ForeignKey, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# ---- controlled vocabularies -------------------------------------------------
# WHY enums: a regulator's dossier must be internally consistent. Making
# dosage_form an enum means the database physically cannot store "Tablets" for a
# capsule product — one whole class of copy-paste bug is designed out, not just
# checked after the fact.


class DosageForm(str, enum.Enum):
    CAPSULE_HARD = "hard gelatin capsule"
    CAPSULE_SOFT = "soft gelatin capsule"
    TABLET = "tablet"
    SYRUP = "syrup"
    INJECTION = "injection"


class RegistrationType(str, enum.Enum):
    NEW = "new"
    RENEWAL = "renewal"
    VARIATION = "variation"


class Region(str, enum.Enum):
    NAFDAC = "NAFDAC"
    FDA = "FDA"
    EU = "EU"


class ExcipientFunction(str, enum.Enum):
    DILUENT = "diluent"
    LUBRICANT = "lubricant"
    DISINTEGRANT = "disintegrant"
    CAPSULE_SHELL = "capsule shell"
    BINDER = "binder"


# ---- product & children ------------------------------------------------------


class Product(Base):
    __tablename__ = "product"

    brand_name: Mapped[str] = mapped_column(String(120))  # LAMOX
    generic_name: Mapped[str] = mapped_column(String(200))  # Amoxicillin
    # strength is stored as the BASE amount (what the label claims):
    strength_mg: Mapped[float] = mapped_column(Numeric(10, 3))  # 500.000
    dosage_form: Mapped[DosageForm] = mapped_column(SAEnum(DosageForm))
    shelf_life_months: Mapped[int] = mapped_column(Integer)  # 24
    storage_statement: Mapped[str] = mapped_column(String(300))
    registration_type: Mapped[RegistrationType] = mapped_column(SAEnum(RegistrationType))
    country: Mapped[str] = mapped_column(String(80), default="Nigeria")

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"))
    project: Mapped["Project"] = relationship(back_populates="product")

    apis: Mapped[list["ActiveIngredient"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    excipients: Mapped[list["Excipient"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    packaging: Mapped[list["Packaging"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    stability: Mapped[list["StabilityStudy"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    clinical: Mapped[list["ClinicalEntry"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    batch_formula: Mapped[list["BatchFormulaLine"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ActiveIngredient(Base):
    __tablename__ = "active_ingredient"
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    inn_name: Mapped[str] = mapped_column(String(200))  # Amoxicillin
    salt_form: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )  # Amoxicillin Trihydrate
    # WHY salt_factor: the API you WEIGH (trihydrate) is heavier than the base
    # the label CLAIMS. 500 mg base -> ~574 mg trihydrate. Storing the factor
    # lets the validator reconcile the batch quantity (see rule R04). Without
    # it, the 144 kg figure in the dossier can never be checked by software.
    salt_factor: Mapped[float] = mapped_column(Numeric(6, 4), default=1.0)  # ~1.148
    compendial_std: Mapped[str] = mapped_column(String(20))  # "BP"

    product: Mapped["Product"] = relationship(back_populates="apis")


class Excipient(Base):
    __tablename__ = "excipient"
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    name: Mapped[str] = mapped_column(String(200))
    function: Mapped[ExcipientFunction] = mapped_column(SAEnum(ExcipientFunction))
    grade: Mapped[str] = mapped_column(String(40))  # "BP"
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    compendial_status: Mapped[str] = mapped_column(String(40))

    product: Mapped["Product"] = relationship(back_populates="excipients")


class Packaging(Base):
    __tablename__ = "packaging"
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    role: Mapped[str] = mapped_column(String(40))  # "primary"/"secondary"/...
    description: Mapped[str] = mapped_column(String(300))

    product: Mapped["Product"] = relationship(back_populates="packaging")


class StabilityStudy(Base):
    __tablename__ = "stability_study"
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    condition: Mapped[str] = mapped_column(String(60))  # "long-term 30C/65RH"
    duration_months: Mapped[int] = mapped_column(Integer)  # 24
    result_summary: Mapped[str] = mapped_column(Text)

    product: Mapped["Product"] = relationship(back_populates="stability")


class ClinicalEntry(Base):
    __tablename__ = "clinical_entry"
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    kind: Mapped[str] = mapped_column(String(60))  # "bioequivalence"
    reference_product: Mapped[str | None] = mapped_column(String(200), nullable=True)
    summary: Mapped[str] = mapped_column(Text)

    product: Mapped["Product"] = relationship(back_populates="clinical")


class BatchFormulaLine(Base):
    """One row of the 3.2.P.1 composition table.

    This is what rules R01/R02/R04 actually read. Per-unit quantity plus batch
    size lets us reconstruct — and check — the batch quantity deterministically.
    """

    __tablename__ = "batch_formula_line"
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    component: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(default=False)
    spec: Mapped[str] = mapped_column(String(40))  # "BP"
    qty_per_unit_mg: Mapped[float] = mapped_column(Numeric(12, 4))
    batch_size_units: Mapped[int] = mapped_column(Integer)  # 250000
    declared_batch_qty_kg: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="batch_formula")


# ---- sections (the documents' narrative, for consistency scanning) -----------


class Section(Base):
    """A CTD section's rendered narrative text.

    In the full platform this text is produced by the template engine (data
    slots) + approved LLM narrative (P05). Here we store it so the validation
    engine can scan what a section actually *says* against the structured data —
    which is how rules R01/R02/R03 catch the LAMOX copy-paste bugs.
    """

    __tablename__ = "section"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"))

    number: Mapped[str] = mapped_column(String(20))  # "3.2.P.1"
    title: Mapped[str] = mapped_column(String(200))
    narrative_text: Mapped[str] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="sections")


class Project(Base):
    __tablename__ = "project"

    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[Region] = mapped_column(SAEnum(Region), default=Region.NAFDAC)

    product: Mapped["Product"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    sections: Mapped[list["Section"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
