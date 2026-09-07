"""Bioequivalence as data: the study, the comparator it was run against,
and the confidence intervals that decide it (P22).

## Why this table exists at all

For a multisource (generic) filing, leaf 5.3.1.2 carries the ENTIRE
scientific argument for approval. Everything in Module 3 says the product
is made consistently and to a specification; only the bioequivalence study
says it behaves in a human being like the product it is copying.

`ClinicalEntry` modelled that as `kind` + `reference_product` + a free-text
`summary`. Rule R06 could therefore check exactly one thing: that a row
exists. It could not check that the 90 % confidence interval for Cmax sits
inside the accepted window, could not check that the comparator named in
the study is the one named in the application form, and -- the part that
made the gap undeniable -- leaf **1.4.1, the Bioequivalence Trial
Information form, is generated ENTIRELY from study data**, so it could not
be produced at all. A Module 1 document built with no prose out of Module 5
numbers is the clearest demonstration in this platform of why the
single-source-of-truth premise matters; a paragraph cannot produce one.

## The three tables, and why they are three

`ReferenceProduct` is a **reference, not a string**. The comparator has an
identity (brand, strength, manufacturer, country of origin) and a physical
instance (the batch actually bought, and its expiry). An assessor checks
that the batch was in date when it was dosed, and that the brand is the
one the application claims equivalence to. None of that is checkable
against a sentence. It hangs off the Product rather than off the study
because two studies -- a fasting one and a fed one -- routinely dose the
same comparator batch, and re-entering it per study is re-entering it
wrongly once.

`BioequivalenceStudy` is the design and the conduct: who ran it, on how
many subjects, in what state, measuring what.

`BioequivalenceResult` is one row per pharmacokinetic parameter, each with
its geometric mean ratio and the two bounds of its 90 % confidence
interval. One row per parameter rather than six columns on the study,
because the verdict is per parameter -- rule R25's finding has to name
Cmax and the bound that failed, not "the study".

## The claim and the evidence, kept apart on purpose

`Product.reference_product_name` / `.reference_product_manufacturer` are
what the APPLICATION declares: the comparator printed on the registration
form (1.2) and in the quality overall summary (2.3). The
`ReferenceProduct` row is what the STUDY actually dosed. They are stored
separately and reconciled by rule R26.

That is not an oversight, it is the same shape `Product.shelf_life_months`
already has against the stability data: the claim lives on the product,
the evidence lives in the data, and a rule refuses to let them disagree.
Collapsing the two into one field would make R26 vacuous -- and the real
filing error it catches (the dossier names one brand throughout and the
CRO dosed another) would become unrepresentable in the model while
remaining perfectly possible in the paperwork.

## Biowaiver

`Biowaiver` is the other route to the same conclusion, and P17's
applicability machinery is what makes it a choice rather than a second
document: answering "yes" to leaf 1.2.17 or 1.2.18 is what makes that leaf
applicable, and this row is what the leaf is rendered FROM.

Its `strength` is a plain string, and that is the phase's scale finding
made visible rather than hidden -- see the field's own comment.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import (
    BEDoseRegimen,
    BEFedState,
    BEStudyDesign,
    BiowaiverKind,
    PKParameter,
)

if TYPE_CHECKING:
    from app.models.batch_analysis import BatchAnalysis
    from app.models.product import Product


class ReferenceProduct(Base):
    """The comparator, as an entity with an identity and a batch.

    Every field here appears on the Bioequivalence Trial Information form
    (1.4.1), which is why the model carries all of them rather than a name
    and a shrug: the BTI form asks for the innovator product, its source
    country, the batch number used and that batch's expiry date, and a form
    generated from data can only ask for what the data holds.
    """

    __tablename__ = "reference_product"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    # The comparator's IDENTITY -- what makes it the right comparator.
    name: Mapped[str] = mapped_column(String(200))
    strength: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # WHY the country matters enough to be its own column: agencies do not
    # accept just any pack of the brand. The comparator is expected to be
    # sourced from a well-regulated market (and NAFDAC, like WHO, looks for
    # the innovator product as marketed in a reference market), so "bought
    # locally" and "bought in the EU" are different regulatory answers.
    country_of_origin: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # The comparator's physical INSTANCE -- what was actually dosed.
    batch_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # An assessor checks this against the study's dosing dates. A comparator
    # dosed after its expiry invalidates the study, and it is a real finding:
    # a date column can be checked, a sentence saying "in date" cannot.
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_country: Mapped[str | None] = mapped_column(String(80), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="reference_products")
    studies: Mapped[list["BioequivalenceStudy"]] = relationship(back_populates="reference_product")

    @property
    def identity(self) -> str:
        """Brand and maker, as one comparable string.

        Used by rule R26 and printed wherever the comparator is named. It
        deliberately omits the batch: two studies dosing two batches of the
        same brand name the SAME comparator, and a check that treated them
        as different would fire on an ordinary filing.
        """
        if self.manufacturer:
            return f"{self.name} ({self.manufacturer})"
        return self.name


class BioequivalenceStudy(Base):
    """One comparative bioavailability / bioequivalence study.

    Hangs off the Product rather than the Project: a study is a fact about
    the medicine, and the same study supports a NAFDAC filing and an FDA
    one. Same reasoning as every other Product child (see app/models/
    product.py).
    """

    __tablename__ = "bioequivalence_study"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    # The CRO's protocol number. An assessor uses this token to tie the
    # tabular listing (5.2), the BTI form (1.4.1) and the study report
    # itself (5.3.1.2) together, so it is filed as data rather than left
    # inside the report's cover page.
    study_identifier: Mapped[str] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)

    design: Mapped[BEStudyDesign] = mapped_column(SAEnum(BEStudyDesign))
    fed_state: Mapped[BEFedState] = mapped_column(SAEnum(BEFedState))
    dose_regimen: Mapped[BEDoseRegimen] = mapped_column(SAEnum(BEDoseRegimen))

    # Enrolled and completed are BOTH recorded, and the difference is the
    # point: dropouts are what an assessor checks the study's power against.
    # A 24-subject study that finished with 16 is not a 24-subject study.
    subjects_enrolled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subjects_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # WHAT was measured in plasma. For a prodrug or a drug with an active
    # metabolite this is a real regulatory question -- measuring the parent
    # when the guidance asks for the metabolite makes the whole study
    # unusable -- so it is a field, not a line in the report.
    analyte: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bioanalytical_method: Mapped[str | None] = mapped_column(String(300), nullable=True)

    cro_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    study_site: Mapped[str | None] = mapped_column(String(300), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # WHICH COMPARATOR. A foreign key, so the BTI form and the tabular
    # listing print the same comparator the dossier declares elsewhere --
    # they cannot each hold their own copy and drift.
    reference_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reference_product.id"), nullable=True
    )

    # WHICH TEST BATCH. A foreign key to the batch whose analysis is filed
    # at 3.2.P.5.4, for exactly the reason StabilityStudy points at one: an
    # assessor cross-references the batch number between the BE study and
    # the batch analysis table, and a string here would let the two
    # sections name different material with nothing to notice.
    test_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("batch_analysis.id"), nullable=True
    )
    # The test batch's size, AS A NUMBER, and this is not a duplicate of
    # `BatchAnalysis.batch_size`. That field is the size as reported
    # ("250,000 capsules"), which is right for a table an assessor reads
    # and useless for arithmetic. Rule R27 has to divide this by the
    # commercial batch size in 3.2.P.3.2, so it needs a number -- the same
    # reason `BatchFormulaLine.batch_size_units` is an integer.
    test_batch_size_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    test_batch_manufacture_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="bioequivalence_studies")
    reference_product: Mapped["ReferenceProduct | None"] = relationship(back_populates="studies")
    test_batch: Mapped["BatchAnalysis | None"] = relationship(
        back_populates="bioequivalence_studies"
    )
    results: Mapped[list["BioequivalenceResult"]] = relationship(
        back_populates="study",
        cascade="all, delete-orphan",
        # By the parameter's declared order, which is the order the BTI
        # form and every BE report print them in: Cmax, then AUC(0-t), then
        # AUC(0-inf). Sorting by the stored string would put AUC first and
        # make every generated table disagree with every study report.
        order_by="BioequivalenceResult.sort_order",
    )

    @property
    def dropouts(self) -> int | None:
        if self.subjects_enrolled is None or self.subjects_completed is None:
            return None
        return self.subjects_enrolled - self.subjects_completed

    @property
    def design_summary(self) -> str:
        """The one-line description 5.2's tabular listing prints.

        Assembled here rather than in the renderer so the tabular listing
        and the BTI form cannot describe the same study differently.
        """
        return f"{self.design.value}, {self.dose_regimen.value}, {self.fed_state.value}"


class BioequivalenceResult(Base):
    """One pharmacokinetic parameter's answer: the ratio and its interval.

    ## Why the confidence interval is stored and the verdict is not

    `ci_lower` and `ci_upper` are the study's own output -- the CRO's
    statistician computed them and the report states them, so they are
    data. Whether they PASS is a judgement against an acceptance window
    that lives in region config and differs for a narrow-therapeutic-index
    drug (see app/ctd/region_profiles.py). Storing a pass/fail boolean
    would freeze one region's window into every row, and widen the window
    in config without re-judging anything already on file.

    Same call `StabilityResult.meets_criterion` makes for the same reason:
    a stored verdict is a second copy of a decision the criterion already
    determines, and the two can disagree.
    """

    __tablename__ = "bioequivalence_result"

    bioequivalence_study_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bioequivalence_study.id")
    )

    parameter: Mapped[PKParameter] = mapped_column(SAEnum(PKParameter))

    # All three are PERCENTAGES of the reference (test/reference x 100), to
    # two decimal places, because that is how the acceptance window is
    # written: 80.00 - 125.00 %. Numeric rather than float so 124.99 does
    # not become 124.99000000000001 on the way to a comparison that decides
    # whether a product is approvable.
    geometric_mean_ratio: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    ci_lower: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    ci_upper: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    # Intra-subject coefficient of variation, as a percentage. Optional,
    # and the reason it is here at all: it is the evidence that decides
    # whether a drug counts as highly variable, which is the argument for
    # any widened window. A finding about a failed Cmax is much more useful
    # beside it.
    intra_subject_cv: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)

    # Presentation order only, denormalised from the parameter's declared
    # order at write time. Every verdict reads the parameter itself, so
    # drift here mis-orders a table and mis-checks nothing -- the same
    # discipline BatchAnalysisResult.sort_order records.
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    study: Mapped["BioequivalenceStudy"] = relationship(back_populates="results")

    def outside(self, lower: Decimal, upper: Decimal) -> list[str]:
        """Which bounds of this interval fall outside `lower`-`upper`.

        Returns the bound NAMES rather than a boolean, because that is what
        rule R25's finding has to say: "the lower bound is 76.40 %" tells a
        filer their study under-performed, while "the upper bound is
        131.00 %" tells them something quite different about the same
        product. A bare False makes the reader go and look.
        """
        breached = []
        if self.ci_lower is not None and Decimal(self.ci_lower) < lower:
            breached.append("lower")
        if self.ci_upper is not None and Decimal(self.ci_upper) > upper:
            breached.append("upper")
        return breached


class Biowaiver(Base):
    """A request to be excused an in vivo study (leaves 1.2.17 and 1.2.18).

    This row is the CONTENT of the request. Whether the request is being
    made at all is answered by P17's applicability machinery -- the filer
    answers "yes" to the conditional leaf, and that is what makes it
    applicable and puts it in the package. Rule R06 refuses to let the two
    disagree, and refuses to let a biowaiver and an in vivo study both be
    filed for the same strength.
    """

    __tablename__ = "biowaiver"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"))

    kind: Mapped[BiowaiverKind] = mapped_column(SAEnum(BiowaiverKind))

    # WHICH STRENGTH this waiver covers -- and it is a STRING, deliberately,
    # because the model cannot yet say anything better.
    #
    # THE SCALE FINDING OF THIS PHASE, recorded here rather than only in the
    # build log, because this is where the next person meets it: a Project
    # points at ONE Product, and a Product's strength lives on its
    # ActiveIngredient rows. There is no product family, so a filing cannot
    # span 5 mg and 10 mg. Leaf 1.2.18 -- "biowaiver request for an
    # ADDITIONAL strength" -- presumes exactly that span, so the platform
    # can record the claim and print the request, and cannot cross-check the
    # other strength's composition or dissolution because the other strength
    # is not in the filing.
    #
    # When Product grows a family, this becomes a foreign key and the
    # proportionality checks that leaf really wants become possible. Until
    # then a string is the honest representation of a fact the model holds
    # only as text.
    strength: Mapped[str] = mapped_column(String(120))

    # BCS class 1-4. Only meaningful for a BCS-based waiver: class 1 (high
    # solubility, high permeability) and class 3 (high solubility, low
    # permeability) are the two that can be argued at all, and which one it
    # is changes what dissolution evidence is required.
    bcs_class: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The f2 similarity factor from the comparative dissolution profiles.
    # A number, because the acceptance threshold is a number (f2 >= 50), and
    # a claim of similarity with no f2 beside it is the kind of assertion
    # this platform exists to stop being prose.
    dissolution_similarity_f2: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    # For an additional-strength waiver: the in vivo study at the OTHER
    # strength that this request leans on. A foreign key, so the request
    # cannot cite a study the dossier does not contain.
    supporting_study_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bioequivalence_study.id"), nullable=True
    )
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="biowaivers")
    supporting_study: Mapped["BioequivalenceStudy | None"] = relationship()

    @property
    def section_number(self) -> str:
        """The leaf this request is filed at.

        One place, so the renderer, the rule and the applicability answer
        cannot each decide for themselves which number a BCS waiver lives
        at.
        """
        return "1.2.17" if self.kind is BiowaiverKind.BCS_BASED else "1.2.18"
