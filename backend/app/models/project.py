"""Project (AGENTS.md §6): ties a Product to a target region profile and a
set of Sequences.

Project.product_id is a many-to-one FK — Product is reusable master data,
so the same product can be filed as several Projects (e.g. a NAFDAC renewal
now, an FDA submission later). Region only ever drives which builder runs
downstream (P08/P09); the model itself never branches on it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import Region

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.sequence import Sequence


class Project(Base):
    __tablename__ = "project"

    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[Region] = mapped_column(SAEnum(Region), default=Region.NAFDAC)

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))
    product: Mapped["Product"] = relationship(back_populates="projects")

    sequences: Mapped[list["Sequence"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    sections: Mapped[list["Section"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Section(Base):
    """A CTD section's rendered narrative text (P04/P06 scaffolding).

    In the full platform this text comes from the template engine (data
    slots) + approved LLM narrative (P05). Stored here so the validation
    engine can scan what a section actually *says* against the structured
    data — which is how rules R01/R02/R03 catch copy-paste bugs like LAMOX's.
    """

    __tablename__ = "section"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"))

    number: Mapped[str] = mapped_column(String(20))  # "3.2.P.1"
    title: Mapped[str] = mapped_column(String(200))
    narrative_text: Mapped[str] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="sections")
