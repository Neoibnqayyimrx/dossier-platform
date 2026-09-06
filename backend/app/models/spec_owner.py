"""The polymorphic owner shared by SpecificationTest, BatchAnalysis and Impurity.

P20's schema decision, and the one most likely to be revisited -- so the
reasoning is here rather than in a commit message.

## The problem

`SpecificationTest` was foreign-keyed to `active_ingredient`, which made it
drug-substance-only *by construction*. But a specification is the same
artifact wherever it appears: a list of tests, each with a method, an
acceptance criterion and a sort order. The CTD asks for that same table
three times, of three different things -- 3.2.S.4.1 of the drug substance,
3.2.P.4.1 of each excipient, 3.2.P.5.1 of the finished product. Modelling
those as three tables means three editors, three sets of rules, and three
places for the same limit to be written differently. **The inconsistencies
between near-duplicate tables are precisely what this platform exists to
catch**, so building them in is not an option.

## The choice: nullable FK per owner type

Every owned row carries one nullable foreign key per possible owner, plus a
CHECK constraint that exactly one of them is set.

    active_ingredient_id  UUID NULL  REFERENCES active_ingredient(id)
    product_id            UUID NULL  REFERENCES product(id)
    excipient_id          UUID NULL  REFERENCES excipient(id)
    CHECK (<exactly one is non-null>)

## The alternative that was rejected: a discriminator column

The obvious other shape is `owner_type VARCHAR` + `owner_id UUID`, with no
foreign key at all (a column cannot reference three tables). It is the
tidier schema, it never changes when a fourth owner type appears, and it is
what most ORMs' "generic foreign key" recipes reach for.

It was rejected because **`owner_id` cannot be a foreign key, and therefore
the database cannot enforce that the owner exists**. Delete an excipient and
its specification rows survive, pointing at nothing, with no cascade to
clean them up and no constraint violated -- and the first symptom is a
3.2.P.4.1 that renders empty, or worse, a batch analysis checked against a
specification that no longer belongs to anything. That is exactly the class
of silent drift this project's determinism boundary (AGENTS.md 5) exists
to make impossible. Trading referential integrity for schema convenience is
the wrong trade in a system whose entire claim is that its data cannot
disagree with itself.

## What the trade costs

Schema churn. A fourth owner type is a migration: one more column, one more
FK, one widened CHECK, one more entry in `_OWNER_ATTRS` below. That is a
real cost, and it is the honest one to pay -- Module 3 has exactly three
things with a specification, and the list is fixed by ICH M4Q rather than by
this codebase, so the fourth owner is a hypothetical while the orphan rows
are a certainty.

## Two owner spaces, not one

`SpecificationTest` accepts all three owners. `BatchAnalysis` and `Impurity`
accept only two -- a batch and an impurity profile belong to the drug
substance (3.2.S.4.4, 3.2.S.3.2) or to the finished product (3.2.P.5.4,
3.2.P.5.5), and the CTD has no excipient leaf for either. Declaring the
narrower space rather than reusing the wider one keeps the constraint
honest: a row the dossier could never render should not be storable.
"""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy import CheckConstraint

from app.models.enums import SpecificationOwnerKind

# owner kind -> (foreign key column name, relationship attribute name).
# ONE table, read by the constraint builder, by `owner_kind` and by `owner`,
# so the three cannot disagree about what an owner is.
_OWNER_ATTRS: dict[SpecificationOwnerKind, tuple[str, str]] = {
    SpecificationOwnerKind.DRUG_SUBSTANCE: ("active_ingredient_id", "active_ingredient"),
    SpecificationOwnerKind.DRUG_PRODUCT: ("product_id", "product"),
    SpecificationOwnerKind.EXCIPIENT: ("excipient_id", "excipient"),
}


def exactly_one_owner(name: str, *kinds: SpecificationOwnerKind) -> CheckConstraint:
    """A CHECK that exactly one of `kinds`' foreign keys is set.

    Written as a sum of CASE expressions rather than as a chain of
    `(a IS NOT NULL AND b IS NULL AND ...)` clauses: the CASE form stays one
    line longer per owner instead of doubling, and it says what it means --
    count the owners, there must be one.

    WHY a constraint at all, when the application always sets exactly one:
    "the application always" is a claim about today's code paths. A row with
    two owners would render into two sections with the same id and no error
    anywhere; a row with none would silently vanish from every section. The
    database is the only place that can refuse both regardless of which code
    wrote the row -- including a migration, a fixture, or a psql session.
    """
    columns = [_OWNER_ATTRS[kind][0] for kind in kinds]
    counted = " + ".join(f"(CASE WHEN {column} IS NULL THEN 0 ELSE 1 END)" for column in columns)
    return CheckConstraint(f"{counted} = 1", name=name)


class SpecificationOwned:
    """Mixin for a row that belongs to exactly one specification owner.

    Deliberately NOT a SQLAlchemy declarative mixin: it declares no columns.
    Each model spells its own foreign keys and relationships out in full,
    because a `declared_attr` that conditionally emits a column would hide
    the one thing a reader of these tables most needs to see -- which owners
    this table actually accepts. What the mixin contributes is the two
    derived accessors, so "which kind of thing owns this row" is answered
    the same way everywhere.
    """

    # The owners this table accepts, narrowest first. Each subclass sets it.
    __owner_kinds__: ClassVar[tuple[SpecificationOwnerKind, ...]] = ()

    @property
    def owner_kind(self) -> SpecificationOwnerKind:
        """Which kind of thing owns this row, derived from which FK is set.

        Derived rather than stored, which is the point of choosing real
        foreign keys: a stored discriminator is a second copy of a fact the
        columns already carry, and the two can disagree. There is nothing
        here to keep in sync.
        """
        for kind in self.__owner_kinds__:
            if getattr(self, _OWNER_ATTRS[kind][0]) is not None:
                return kind
        # Reachable only for an in-memory object whose owner was assigned
        # through the RELATIONSHIP rather than the id -- SQLAlchemy fills
        # the foreign key at flush, not at assignment, which is the same
        # "Python-side default applies at flush" trap P19 hit with
        # Packaging.role. Fall back to the relationship before giving up.
        for kind in self.__owner_kinds__:
            if getattr(self, _OWNER_ATTRS[kind][1], None) is not None:
                return kind
        raise ValueError(
            f"{type(self).__name__} has no owner set; exactly one of "
            f"{', '.join(_OWNER_ATTRS[k][0] for k in self.__owner_kinds__)} is required."
        )

    @property
    def owner(self):
        """The owning object itself -- an ActiveIngredient, Product or
        Excipient. Used by the rules and the context builders, which care
        about the owner's NAME far more often than about its type."""
        return getattr(self, _OWNER_ATTRS[self.owner_kind][1])

    @property
    def owner_name(self) -> str:
        """What the owner is called, for a finding or a rendered heading.

        Each owner type spells its name differently (`inn_name`, `name`,
        `brand_name`), and every caller that needed one was about to write
        the same three-branch expression.
        """
        owner = self.owner
        for attribute in ("inn_name", "brand_name", "name"):
            value = getattr(owner, attribute, None)
            if value:
                return str(value)
        return str(owner)
