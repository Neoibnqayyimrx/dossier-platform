"""Certificate: a regulatory document a human must obtain from a third
party (a regulator, EDQM, a testing lab) and attach to the dossier.

WHY this is a row that can exist before the real file does: a project's
required certificates are knowable in advance (a NAFDAC generic filing
needs a CPP; a GMP-audited site needs a GMP certificate) even before anyone
has gone and obtained them. Recording "we need a CPP, issued by NAFDAC,
still pending" as a row -- issue_date/expiry_date/certificate_number all
nullable -- lets P06 flag it as missing/expired, and lets P04's assembly
step emit a clearly-marked placeholder document at the right path in the
package, rather than the gap being silent. This is never LLM-generated
content; the LLM cannot write a real regulator's signature.

WHY product_id is required but manufacturer_id is optional: every
certificate belongs to some product's dossier, but only site-specific ones
(GMP) point at a particular Manufacturer -- a CPP or CEP is about the
product/API generally, not one site.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import CertificateType

if TYPE_CHECKING:
    from app.models.manufacturer import Manufacturer
    from app.models.product import Product


class Certificate(Base):
    __tablename__ = "certificate"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))
    manufacturer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("manufacturer.id"), nullable=True
    )

    certificate_type: Mapped[CertificateType] = mapped_column(SAEnum(CertificateType))
    issuing_authority: Mapped[str | None] = mapped_column(String(200), nullable=True)
    certificate_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="certificates")
    manufacturer: Mapped["Manufacturer | None"] = relationship(back_populates="certificates")
