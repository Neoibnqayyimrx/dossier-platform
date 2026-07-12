from __future__ import annotations

from pydantic import BaseModel

from app.models.enums import DosageForm, LegalStatus, RegistrationType
from app.schemas.active_ingredient import ActiveIngredientRead
from app.schemas.base import ReadMixin
from app.schemas.batch_formula import BatchFormulaLineRead
from app.schemas.clinical import ClinicalEntryRead
from app.schemas.excipient import ExcipientRead
from app.schemas.manufacturer import ManufacturerRead
from app.schemas.packaging import PackagingRead
from app.schemas.stability import StabilityStudyRead


class ProductBase(BaseModel):
    brand_name: str
    generic_name: str
    strength_value: float | None = None
    strength_unit: str | None = None
    dosage_form: DosageForm | None = None
    atc_code: str | None = None
    shelf_life_months: int | None = None
    storage_condition: str | None = None
    pack_size: str | None = None
    route_of_administration: str | None = None
    legal_status: LegalStatus | None = None
    registration_type: RegistrationType | None = None
    country: str | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    brand_name: str | None = None
    generic_name: str | None = None
    strength_value: float | None = None
    strength_unit: str | None = None
    dosage_form: DosageForm | None = None
    atc_code: str | None = None
    shelf_life_months: int | None = None
    storage_condition: str | None = None
    pack_size: str | None = None
    route_of_administration: str | None = None
    legal_status: LegalStatus | None = None
    registration_type: RegistrationType | None = None
    country: str | None = None


class ProductRead(ProductBase, ReadMixin):
    """Nests every child collection — this is what the document-generation
    templates (P04) and builders (P08/P09) read to render a full section."""

    manufacturers: list[ManufacturerRead] = []
    apis: list[ActiveIngredientRead] = []
    excipients: list[ExcipientRead] = []
    packaging: list[PackagingRead] = []
    stability: list[StabilityStudyRead] = []
    clinical: list[ClinicalEntryRead] = []
    batch_formula: list[BatchFormulaLineRead] = []
