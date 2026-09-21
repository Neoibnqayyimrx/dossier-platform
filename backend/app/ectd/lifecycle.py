"""Lifecycle resolver (P09) -- the highest-risk logic in the whole phase,
per the reference doc.

Two things this returns, deliberately kept distinct:

- `backbone_leaves`: what THIS sequence's own `index.xml`/`eu-regional.xml`
  should list. Per real eCTD semantics, an UNCHANGED document is entirely
  OMITTED here -- a reviewer's tool reconstructs current state by
  replaying every sequence in order, so a leaf a sequence never mentions
  is simply still whatever the last sequence that DID mention it said.
  Naive designs commonly get this wrong by "just restating everything
  every time"; the omission is deliberate, not a gap.

- `cumulative_leaves`: the FULL current-state view of the dossier as of
  this sequence -- every leaf that's still live, whether or not this
  sequence's own backbone restated it. This is what gets persisted as
  THIS sequence's `SequenceLeaf` rows, so the NEXT sequence's resolver has
  something complete to diff against even when a given document hasn't
  changed in several sequences running. Persisting only `backbone_leaves`
  instead would silently lose history the moment one sequence goes by
  without touching a given document.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ectd.leaf import Leaf, leaf_id_for


@dataclass(frozen=True)
class PriorLeaf:
    """The cumulative-state record of one live document as of some
    sequence -- a plain dataclass (no SQLAlchemy/session dependency) so
    this module stays trivially unit-testable. Maps 1:1 onto the columns
    `app.models.sequence_leaf.SequenceLeaf` persists."""

    section_key: str
    leaf_id: str
    title: str
    path: str  # relative to the sequence that introduced/last changed it
    checksum: str
    operation: str  # the operation that was in force as of that sequence
    # The ID of the leaf that operation modified -- see `Leaf.modifies`.
    modifies: str | None = None


@dataclass(frozen=True)
class NewLeafInput:
    """One leaf as it exists in the CURRENT build, before any lifecycle
    decision has been applied."""

    section_key: str
    title: str
    path: str  # relative to the new sequence's own root
    checksum: str


@dataclass(frozen=True)
class LifecycleResult:
    backbone_leaves: dict[str, Leaf]
    cumulative_leaves: dict[str, PriorLeaf]


def resolve_lifecycle(
    prior_cumulative_leaves: list[PriorLeaf],
    new_leaves: list[NewLeafInput],
    sequence_number: str,
) -> LifecycleResult:
    """`prior_cumulative_leaves` is `[]` for a project's very first
    sequence: everything is `new` and there is nothing to diff against.

    WHY this no longer takes the prior sequence's number (gap Phase 4a): it
    was used for one thing, building `modified-file`, and it was the wrong
    input for it. A replaced document's earlier leaf lives in whichever
    sequence last CHANGED it, which is the immediately prior sequence only
    by coincidence. The leaf ID carries its own sequence
    (`app.ectd.leaf.sequence_number_of`), so the correct answer needs no
    parameter at all.
    """
    prior_by_key = {p.section_key: p for p in prior_cumulative_leaves}
    new_by_key = {n.section_key: n for n in new_leaves}

    backbone: dict[str, Leaf] = {}
    cumulative: dict[str, PriorLeaf] = {}

    for key, new_leaf in new_by_key.items():
        prior = prior_by_key.get(key)
        leaf_id = leaf_id_for(key, sequence_number)

        if prior is None:
            backbone[key] = Leaf(
                id=leaf_id,
                title=new_leaf.title,
                href=new_leaf.path,
                checksum=new_leaf.checksum,
                operation="new",
            )
            cumulative[key] = PriorLeaf(
                section_key=key,
                leaf_id=leaf_id,
                title=new_leaf.title,
                path=new_leaf.path,
                checksum=new_leaf.checksum,
                operation="new",
            )
        elif prior.checksum != new_leaf.checksum:
            backbone[key] = Leaf(
                id=leaf_id,
                title=new_leaf.title,
                href=new_leaf.path,
                checksum=new_leaf.checksum,
                operation="replace",
                modifies=prior.leaf_id,
            )
            cumulative[key] = PriorLeaf(
                section_key=key,
                leaf_id=leaf_id,
                title=new_leaf.title,
                path=new_leaf.path,
                checksum=new_leaf.checksum,
                operation="replace",
                modifies=prior.leaf_id,
            )
        else:
            # Unchanged: omitted from this sequence's own backbone, but
            # the cumulative view carries the OLD record forward as-is --
            # the file still physically lives in the old sequence's
            # directory; nothing about it changed in this sequence.
            cumulative[key] = prior

    for key, prior in prior_by_key.items():
        if key in new_by_key:
            continue
        # A retired document. The leaf announces the retirement and names
        # what it retires; it carries no file. This used to restate the old
        # href and checksum on the belief that the DTD required both -- it
        # requires the checksum ATTRIBUTE, but leaves xlink:href IMPLIED,
        # and the ICH spec (v3.2.2, Appendix 6) says a delete's checksum
        # "will be empty". Restating the href also pointed at a path inside
        # THIS sequence where no file exists, so our own M05 check failed
        # every delete this resolver ever produced.
        backbone[key] = Leaf(
            id=leaf_id_for(key, sequence_number),
            title=prior.title,
            href=None,
            checksum="",
            operation="delete",
            modifies=prior.leaf_id,
        )
        # Deleted -- drops out of the cumulative view, not carried forward.

    return LifecycleResult(backbone_leaves=backbone, cumulative_leaves=cumulative)
