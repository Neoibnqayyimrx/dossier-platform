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

from sqlalchemy import JSON, String, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import FDAApplicationType, Region, SubmissionType

if TYPE_CHECKING:
    from app.models.applicant import Applicant
    from app.models.declaration import Declaration
    from app.models.product import Product
    from app.models.correspondence import Correspondence
    from app.models.section_document import SectionDocument
    from app.models.sequence import Sequence
    from app.models.narrative import NarrativeGeneration
    from app.models.validation_override import ValidationOverride


class Project(Base):
    __tablename__ = "project"

    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[Region] = mapped_column(SAEnum(Region), default=Region.NAFDAC)

    # P17. WHY on Project and not on Product: the same product can be filed
    # generically in one market and as a full application in another, so
    # "how much of the CTD does this owe" is a property of the FILING, not
    # of the medicine -- exactly the reasoning that put `applicant` here in
    # P15a. The default keeps every project created before P17 declaring
    # the scope the platform already assumed it had.
    submission_type: Mapped[SubmissionType] = mapped_column(
        SAEnum(SubmissionType), default=SubmissionType.MULTISOURCE_GENERIC
    )

    # Answers to the CONDITIONAL sections' yes/no questions, keyed by
    # section number ("1.2.15" -> False). True means "yes, this applies to
    # my filing"; False means "no", which is what makes the platform emit
    # the not-applicable statement; a number simply absent means nobody has
    # answered yet, which rule R19 reports as a WARNING.
    #
    # WHY a JSON column rather than a ProjectCondition child table: the KEYS
    # are section numbers owned by the region profile's applicability table
    # (config), not a fixed enum the database could constrain, so a table
    # would buy an FK it cannot actually enforce plus a migration every time
    # a condition is added to config. The rejected alternative is recorded
    # in the P17 build-log entry along with what would change our mind: the
    # day an answer needs an author and a timestamp (i.e. becomes an
    # auditable regulatory assertion rather than a scoping switch), it earns
    # its own table.
    condition_answers: Mapped[dict[str, bool]] = mapped_column(
        JSON, default=dict, server_default="{}"
    )

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))
    product: Mapped["Product"] = relationship(back_populates="projects")

    # Nullable: a project can exist before its applicant is captured --
    # completeness for a NAFDAC filing is R14's job, not a schema constraint.
    applicant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applicant.id"), nullable=True
    )
    applicant: Mapped["Applicant | None"] = relationship(back_populates="projects")

    # gap Phase 4b: the agency-assigned application number, and for FDA
    # which kind of application it numbers. FDA's backbone carries both on
    # every sequence ("ANDA 123456" is `application-type="fdaat2"` +
    # `123456`). The agency issues the number; this platform never makes
    # one up, which is why rule R34 blocks an FDA export without it rather
    # than the builder inventing a placeholder.
    #
    # WHY on Project for now: gap.md Phase 6 introduces an `Application`
    # entity between Product and Project/Sequence, and it is the natural
    # home for both. They live here until then, deliberately named so the
    # Phase 6 migration is a move rather than a reinterpretation.
    application_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fda_application_type: Mapped[FDAApplicationType | None] = mapped_column(
        SAEnum(FDAApplicationType), nullable=True
    )

    def __init__(self, **kwargs) -> None:
        """Apply P17's defaults at CONSTRUCTION, not just at INSERT.

        WHY: `mapped_column(default=...)` fires when SQLAlchemy flushes the
        row, so a Project that has been built but not yet committed has
        `submission_type = None` -- and every reader of applicability
        (assembly, the rules, the section list) would then see a project
        with no declared scope at all. That is precisely the "we don't know
        what this dossier owes" state P17 exists to eliminate, so it should
        not be reachable even for the few milliseconds before a commit.
        """
        kwargs.setdefault("submission_type", SubmissionType.MULTISOURCE_GENERIC)
        kwargs.setdefault("condition_answers", {})
        # P18: start the uploaded-documents collection LOADED and empty.
        #
        # WHY: rule R20 reads `project.documents`, and on a project that was
        # built in Python and then committed, that collection has never been
        # loaded -- so the attribute access goes to the database. Under the
        # async engine, IO from a plain attribute access does not merely
        # block, it raises MissingGreenlet. Initialising it here means the
        # rules can read it the way they read every other field.
        #
        # (Objects loaded from a query are unaffected: SQLAlchemy does not
        # call `__init__` when it materialises a row, and the relationship's
        # own `lazy="selectin"` loads it there.)
        kwargs.setdefault("documents", [])
        super().__init__(**kwargs)

    sequences: Mapped[list["Sequence"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    sections: Mapped[list["Section"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    narrative_generations: Mapped[list["NarrativeGeneration"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    validation_overrides: Mapped[list["ValidationOverride"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    declarations: Mapped[list["Declaration"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    # P18: the real files a human has attached to this filing's leaves.
    # `lazy="selectin"` for the same reason every other project child is
    # eagerly loaded (app/api/loading.py): the validation rules and the
    # builders both walk these outside a request's await points, and a lazy
    # load there raises under async SQLAlchemy rather than merely being slow.
    documents: Mapped[list["SectionDocument"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    # P27: the conversation with the agency about this filing. NOT
    # lazy="selectin" like documents above -- nothing in the build path
    # reads correspondence, so loading it on every project read would be
    # work no builder needs.
    correspondence: Mapped[list["Correspondence"]] = relationship(
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
