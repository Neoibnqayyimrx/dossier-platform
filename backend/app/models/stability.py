"""Stability as data: the study, its axes, and its timepoint results.

## What was wrong with the old shape

`StabilityStudy` was one row per study -- type, condition, duration, and a
`result_summary` string -- hanging off the Product. Three things were
wrong with that, and each of them is a section the dossier owes:

1. **It was drug-product-only.** 3.2.S.7 is the DRUG SUBSTANCE's stability,
   filed per substance; 3.2.P.8 is the finished product's. One product FK
   could only ever answer one of them, so a combination product's two
   actives had nowhere to put their data at all.
2. **It flattened the study's real axes.** A stability study is run on a
   named BATCH, at a storage CONDITION, in a specific PACK PRESENTATION.
   3.2.P.8.3's tables are organised along exactly those axes -- an
   assessor reads "batch X, 30C/65%RH, blister" as one column of data --
   and a model that carries only the condition cannot produce them.
3. **The results were prose.** `result_summary` said "Within specification
   through 24 months". A sentence cannot be rendered as the timepoint x
   test table 3.2.S.7.3 and 3.2.P.8.3 ARE, and -- the part that matters --
   it cannot be checked. It can say "within specification" while the
   dissolution at 6 months was 68 % against an NLT 80 % limit, and nothing
   in the platform would know.

## What replaced it

The owner is the same two-owner polymorphism `BatchAnalysis` uses (see
app/models/spec_owner.py): a study is a study OF the drug substance
(3.2.S.7) or OF the finished product (3.2.P.8), and the CTD has no third
place to file one.

The batch is a foreign key to `BatchAnalysis`, not a re-typed batch
number. That is deliberate and it is worth more than it looks: ICH Q1A(R2)
asks for stability data on the SAME primary batches whose analysis is
filed in 3.2.S.4.4 / 3.2.P.5.4, and an assessor cross-references those
batch numbers between the two sections. A string here would let the two
sections name different batches with nothing to notice; the key cannot.

The pack is a foreign key to `Packaging`, because "as marketed" is the
whole point of the section -- ICH Q1A(R2) requires stability data in the
container closure system proposed for marketing, and a shelf life
supported in a drum does not support a blister.

`result_summary` is gone. What replaced it is `StabilityResult` below,
plus a NOTES field that is never rendered as the section's conclusion --
see the migration for why the text is kept but demoted.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import SpecificationOwnerKind, StabilityStudyType
from app.models.spec_owner import SpecificationOwned, exactly_one_owner
from app.validation.acceptance import evaluate

if TYPE_CHECKING:
    from app.models.active_ingredient import ActiveIngredient
    from app.models.batch_analysis import BatchAnalysis
    from app.models.packaging import Packaging
    from app.models.product import Product
    from app.models.specification import SpecificationTest


class StabilityStudy(Base, SpecificationOwned):
    __tablename__ = "stability_study"

    __owner_kinds__ = (
        SpecificationOwnerKind.DRUG_SUBSTANCE,
        SpecificationOwnerKind.DRUG_PRODUCT,
    )
    __table_args__ = (exactly_one_owner("ck_stability_study_one_owner", *__owner_kinds__),)

    # NULLABLE now, where every pre-P21 row set it. The migration widens
    # rather than replaces -- every study on file stays a drug-product
    # study with the product_id it had, which is what makes R05's existing
    # tests pass untouched.
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product.id"), nullable=True)
    active_ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("active_ingredient.id"), nullable=True
    )

    study_type: Mapped[StabilityStudyType] = mapped_column(SAEnum(StabilityStudyType))
    # The storage condition as ICH Q1A(R2) states it: "30C/65%RH",
    # "40C/75%RH". Text, like an acceptance criterion, because the real
    # vocabulary is wider than a temperature and a humidity -- refrigerated
    # products, "protected from light", and the zone IVb condition all
    # appear -- and a pair of numeric columns would have to drop the rest.
    condition: Mapped[str] = mapped_column(String(80))
    # How long the study has RUN. Distinct from the shelf life claimed
    # (Product.shelf_life_months) and from the longest passing timepoint,
    # which is what R05 now actually checks against -- a study can run 24
    # months and fail at 12.
    duration_months: Mapped[int] = mapped_column(Integer)
    # WHICH BATCH. A real foreign key to the batch whose analysis is filed
    # in 3.2.S.4.4 / 3.2.P.5.4 -- see the module docstring. Nullable only
    # because a study may predate its batch being entered; rule R23's
    # findings name the batch when it is there.
    batch_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("batch_analysis.id"), nullable=True
    )
    # WHICH PACK. "In the container closure system proposed for marketing"
    # is a requirement, not a detail (ICH Q1A(R2) 2.2.5): the same batch in
    # a blister and in an HDPE bottle are two studies with two answers.
    packaging_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("packaging.id"), nullable=True
    )
    protocol: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What was `result_summary`, demoted. It is kept so no filer's text is
    # thrown away by the migration, and it is NEVER rendered as the
    # section's conclusion: a typed summary printed above a computed table
    # is the contradiction this phase exists to remove. 3.2.S.7.1 and
    # 3.2.P.8.1 are built from `results` below.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped["Product | None"] = relationship(back_populates="stability")
    active_ingredient: Mapped["ActiveIngredient | None"] = relationship(
        back_populates="stability"
    )
    batch_analysis: Mapped["BatchAnalysis | None"] = relationship(
        back_populates="stability_studies"
    )
    packaging: Mapped["Packaging | None"] = relationship()

    results: Mapped[list["StabilityResult"]] = relationship(
        back_populates="study",
        cascade="all, delete-orphan",
        # By timepoint first, then by the specification's own row order:
        # that is how a stability table is read -- down a timepoint's
        # column, in specification order -- and it is the order the
        # renderer must produce byte-identically on every build.
        order_by="(StabilityResult.timepoint_months, StabilityResult.sort_order)",
    )

    @property
    def first_failing_timepoint(self) -> int | None:
        """The earliest timepoint at which any test was decided against.

        Only a result the acceptance criterion actually settles counts:
        `evaluate` returning False. A result that cannot be read
        mechanically returns None and does NOT condemn its timepoint --
        the same three-outcome discipline app/validation/acceptance.py is
        built on, where None never means "passed" but must also never
        mean "failed".
        """
        failures = [result.timepoint_months for result in self.results if result.fails()]
        return min(failures) if failures else None

    @property
    def longest_passing_timepoint(self) -> int | None:
        """How far this study actually supports: the last timepoint BEFORE
        the first failure, or the last one on file if nothing failed.
        None means the study has no timepoint results at all.

        WHY not simply "the greatest timepoint with no failure": a product
        that fails dissolution at 6 months and passes again at 12 has not
        recovered. It has an out-of-specification result, and everything
        after it is data about material that already went out of
        specification. Reading the later pass as support would let a single
        mid-study failure be stepped over -- exactly the defect 3.2.P.8.3
        exists to make visible.

        None and 0 are different answers and callers must keep them apart:
        None means "no results on file", 0 means "results on file, and they
        support nothing" -- a study that failed at its first timepoint.
        """
        if not self.results:
            return None
        timepoints = sorted({result.timepoint_months for result in self.results})
        first_failure = self.first_failing_timepoint
        if first_failure is None:
            return timepoints[-1]
        before = [t for t in timepoints if t < first_failure]
        return before[-1] if before else 0

    @property
    def timepoints(self) -> list[int]:
        """Every timepoint tested, in order. The columns of the rendered
        3.2.S.7.3 / 3.2.P.8.3 table."""
        return sorted({result.timepoint_months for result in self.results})


class StabilityResult(Base):
    """One test, at one timepoint, in one study.

    ## Why it points at a SpecificationTest

    Identical reasoning to `BatchAnalysisResult`, and the phase depends on
    it: the limit a stability result is judged against is not a copy of the
    specification's limit, it IS the specification's limit, reached through
    `specification_test`. Tighten a limit in 3.2.P.5.1 and every timepoint
    already on file is re-judged with nothing re-entered.

    It also makes a whole class of error unrepresentable. A stability table
    can only report tests that are in the specification, because there is
    no other row to point at -- so "we tested dissolution on stability but
    the specification has no dissolution limit" becomes a thing you cannot
    file, rather than a thing an assessor finds.

    ## Why `meets_criterion` is derived rather than stored

    The phase brief asks the model to carry "whether it meets the
    criterion". It does -- as a property, computed from the criterion and
    the result, not as a column.

    A stored boolean is a second copy of a judgement the acceptance
    criterion already determines, and the two can disagree: edit the limit
    and the stored verdict is silently stale, which is the exact failure
    the foreign key above exists to prevent one level down. Deriving it
    costs a regex per read and makes the disagreement unrepresentable.
    """

    __tablename__ = "stability_result"

    stability_study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stability_study.id"))
    specification_test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("specification_test.id"))

    # Months since the study started. 0 is the initial timepoint and is a
    # real one -- ICH Q1A(R2)'s testing frequency starts there, and a table
    # with no zero column cannot show that the material started in
    # specification.
    timepoint_months: Mapped[int] = mapped_column(Integer)
    # The value AS REPORTED in the stability report: "99.1 %", "0.4 %",
    # "Complies", "White powder". Text for the same reason the acceptance
    # criterion is text -- half a specification's rows are not numeric.
    result: Mapped[str] = mapped_column(String(300))
    # Denormalised from the specification test's own `sort_order` at write
    # time, so the relationship above can order without a join. Presentation
    # only: every verdict reads the limit through `specification_test`, so
    # drift here mis-orders a table and mis-checks nothing.
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    study: Mapped["StabilityStudy"] = relationship(back_populates="results")
    specification_test: Mapped["SpecificationTest"] = relationship(
        back_populates="stability_results"
    )

    @property
    def meets_criterion(self) -> bool | None:
        """True / False / None, where None means "cannot be decided
        mechanically" and is NEVER a pass. See
        app/validation/acceptance.py's docstring on why the third outcome
        has to stay a third outcome."""
        test = self.specification_test
        if test is None:
            return None
        return evaluate(test.acceptance_criterion, self.result)

    def fails(self) -> bool:
        """Decided against. Written as its own method rather than
        `not meets_criterion` at each call site, because `not None` is True
        and that mistake would read every unparseable result as a failure --
        the loud half of the failure the parser is shaped to avoid."""
        return self.meets_criterion is False


# ---------------------------------------------------------------------------
# What a set of studies actually supports.
#
# WHY this lives on the model layer rather than inside the rule that uses
# it: 3.2.S.7.1 and 3.2.P.8.1 have to RENDER the same number rule R05
# CHECKS, and if the renderer computed its own the summary could state a
# shelf life the data does not support -- which is the exact defect this
# phase exists to remove, reintroduced one layer up. One function, imported
# by both, and a test pins the two together.
# ---------------------------------------------------------------------------


def supported_months(studies) -> tuple[int, str]:
    """How many months `studies` actually support, and on what basis.

    The basis string is not decoration -- it is the difference between "we
    checked every timepoint against its acceptance criterion" and "we took
    the filer's word for how long the study ran", and a filer reading an
    R05 finding needs to know which of those they are arguing with.

    ## The two-part answer, and why it is two parts

    **Reach is the MAXIMUM across studies. A failure anywhere CAPS it.**

    Reach has to be the maximum, because primary batches are put on
    stability as they are made: one batch at 24 months and two at 12
    because they were started later is the ordinary state of an ongoing
    programme, not a defect. Taking the minimum would report a normal
    filing as unsupported.

    The cap has to be global, because a shelf life is a claim about the
    product, not about the luckiest batch. If any primary batch goes out of
    specification at 12 months, the programme has not supported 24 months
    -- "two batches out of three held" is not a shelf life, it is a
    deviation investigation. So the earliest failure across ALL the studies
    is found first, and only timepoints strictly before it can count.

    That combination is what makes 3.2.P.8.1 unable to overstate: the
    summary prints this number, R05 checks against this number, and a
    failure in one batch pulls both down together.

    A study with no timepoint results falls back to its declared duration,
    which is exactly the pre-P21 behaviour: it is the most the platform can
    honestly say about a study whose data has not been entered. It says so
    in the basis rather than pretending the number was checked -- and it is
    ignored entirely once some other study has failed, since a study with
    no data cannot extend a period the data already disproves.
    """
    studies = list(studies)
    failures = [
        study.first_failing_timepoint
        for study in studies
        if study.first_failing_timepoint is not None
    ]
    earliest_failure = min(failures) if failures else None

    best = 0
    basis = "no long-term stability data on file"
    seen = False
    for study in studies:
        if study.results:
            usable = [
                months
                for months in study.timepoints
                if earliest_failure is None or months < earliest_failure
            ]
            months = max(usable, default=0)
            reason = (
                "the longest timepoint at which every test still met its "
                "acceptance criterion"
                if earliest_failure is None
                else (
                    f"the last timepoint before the first out-of-specification "
                    f"result, which is at {earliest_failure} months"
                )
            )
        elif earliest_failure is not None:
            continue
        else:
            months = study.duration_months
            reason = "the declared study duration; no timepoint results are on file to check"
        if not seen or months > best:
            best, basis, seen = months, reason, True
    return best, basis
