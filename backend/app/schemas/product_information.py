"""Product information schemas: the SmPC, the label and the leaflet (P23).

## The most important thing in this file is what is NOT in it

`ProductInformationWrite` has no `shelf_life_months`, no
`storage_condition`, no `strength` and no `pack_size` -- and the model
config below forbids extra fields, so a client that sends one gets a 422
naming it rather than a silent no-op.

That is the API-layer half of the phase's promise. The model layer makes a
second copy of the shelf life unstorable (there is no column); this makes
it unSENDABLE, with an error message that says where the value actually
lives. A filer who tries to type a shelf life onto the SmPC learns that it
comes from the stability data at the moment they try, rather than at export
three weeks later.

WHY `extra="forbid"` rather than Pydantic's default of ignoring unknown
keys: ignoring is the worst of the three options. The write appears to
succeed, the value is dropped, and the filer believes the SmPC now says 36
months. An explicit refusal is the only response that teaches anything.

## Why the read schema carries the derived values anyway

`ProductInformationRead` returns them, each with its provenance, under
`derived`. Read and write are asymmetric on purpose: the wizard has to SHOW
the shelf life on the product information screen -- an SmPC page that
omitted section 6.3 would be baffling -- while making unmistakable that it
is not a field. Showing it read-only with "comes from your stability data"
beside it is what turns a refusal into an explanation.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import AdverseEventFrequency
from app.schemas.base import ORMBase, ReadMixin


class UndesirableEffect(BaseModel):
    """One row of SmPC 4.8, which the leaflet's section 4 prints as well.

    The frequency is the CIOMS band, validated against the enum rather than
    accepted as free text: the bands are defined numerically in the SmPC
    guideline, and both documents are required to print them in band order.
    "fairly often" is not a band, and a document cannot order it.
    """

    effect: str
    frequency: AdverseEventFrequency


class ProductInformationWrite(BaseModel):
    """Everything a filer may set. See this module's docstring for the
    fields that are deliberately absent."""

    model_config = ConfigDict(extra="forbid")

    therapeutic_indications: str | None = None
    posology_and_administration: str | None = None
    contraindications: list[str] = []
    special_warnings: list[str] = []
    interactions: str | None = None
    pregnancy_and_lactation: str | None = None
    effects_on_driving: str | None = None
    undesirable_effects: list[UndesirableEffect] = []
    overdose: str | None = None
    incompatibilities: str | None = None
    special_precautions_for_disposal: str | None = None

    @field_validator("contraindications", "special_warnings")
    @classmethod
    def _reject_blank_entries(cls, entries: list[str]) -> list[str]:
        """A blank contraindication is a bullet with nothing on it, printed
        into a patient leaflet. Stripped and dropped here rather than
        rendered, because the template has no way to tell an empty string
        from a deliberate one."""
        return [entry.strip() for entry in entries if entry and entry.strip()]


class DerivedValue(BaseModel):
    """A value the product information PRINTS but does not own.

    `source` is a sentence, not a field name, because it is shown to the
    filer: "Claimed on the product; your long-term stability data supports
    24 months" answers the question a read-only field provokes.
    """

    field: str
    label: str
    value: str
    source: str
    smpc_section: str | None = None


class ProductInformationRead(ReadMixin, ProductInformationWrite):
    product_id: uuid.UUID
    # Populated by the route from `app.templating.product_information.
    # shared_values` -- the same function the three documents render from,
    # so the wizard shows the filer exactly what will be printed.
    derived: list[DerivedValue] = []

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class DocumentValue(BaseModel):
    """What ONE of the three documents prints for one shared field."""

    section: str
    document: str
    value: str


class ComparisonRow(ORMBase):
    """One shared field, as each of the three documents renders it.

    `agrees` is computed on the server rather than left to the UI: it is a
    regulatory verdict, and rule R31 makes the same call on the same data.
    Two implementations of "do these agree" is exactly the kind of second
    copy this phase exists to remove.
    """

    field: str
    label: str
    smpc_section: str | None = None
    source: str
    values: list[DocumentValue]
    agrees: bool


class ThreeWayComparison(ORMBase):
    """The SmPC, the label and the leaflet compared field by field.

    `divergences` is the count of rows where the three do not agree. It is
    zero by construction today (see app/templating/product_information.py),
    which is the screen's actual message: this is a defect class the filing
    cannot contain, shown rather than asserted.
    """

    rows: list[ComparisonRow]
    divergences: int
