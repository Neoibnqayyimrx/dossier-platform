"""The machinery behind the documents that are DERIVED from other documents
(P24): the Quality Information Summary (1.4.2) and the Quality Overall
Summary (2.3).

## The problem this module exists to solve

A QIS and a QOS are re-presentations of Module 3. Every number on them
already appears somewhere in Module 3, in a different layout and a
different order, for a different reader. In a hand-built dossier they are
typed out a second time -- and that second typing is where dossiers go
wrong. A shelf life extended from 24 to 36 months updates 3.2.P.8.1 and not
the QOS; a specification limit is tightened in 3.2.P.5.1 and the QIS still
carries last year's. An assessor cross-reading the two finds a
contradiction the applicant cannot explain, because nobody chose it.

## The mechanism

`section_contexts(project)` renders **the section contexts Module 3 itself
renders from** -- literally the dicts `app.templating.context.build_context`
hands to docxtpl -- and returns them keyed by instance. The QIS and the QOS
then read their fields out of THOSE DICTS.

Neither derived document is permitted to touch a model attribute. That is
not a convention this module hopes callers follow; it is the only thing
they are given. `field()` raises when a context has no such key, and
`context_for()` raises when the section was never rendered, so a QIS field
with no Module 3 source fails at build time and names itself -- rather than
rendering a blank an assessor has to notice.

WHY this is worth a module of its own rather than a helper inside qis.py:
both derived documents need exactly the same thing, and the property that
matters ("no field is re-entered") is only true if there is ONE way for
them to get a value. Two copies of this function would be two ways.

## What is deliberately NOT derived

The narrative slots. A QOS is a summary with genuine judgement in it --
"the process is a conventional wet granulation and the critical steps are
controlled by the in-process limits in 3.2.P.3.4" is an argument, not a
re-presentation. Those slots are the section's own, generated and approved
like any other narrative. The DATA around them is derived; the summary
sentence is written. Any field that could carry a number is on the derived
side of that line.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.templating.instances import SectionInstance, expand_sections


@dataclass(frozen=True)
class SourcedValue:
    """One derived field, with the Module 3 leaf it was taken from.

    `source` is printed in the rendered document, beside the value. That is
    a regulatory courtesy and an engineering one at once: an assessor
    reading a QIS field can go straight to the Module 3 section that
    justifies it, and a reviewer of THIS CODE can see at a glance that the
    field came from somewhere rather than from a form.
    """

    label: str
    value: str
    source: str


def section_contexts(project) -> dict[str, dict]:
    """Every section context this project renders, keyed by instance key.

    Keyed by INSTANCE ("3.2.S.1-ampicillin"), not by section number, because
    a combination product has two of several of these and a QIS owes a block
    per drug substance. `expand_sections` is the same expansion assembly
    walks, so a section that would not be emitted into the package -- a
    conditional biowaiver, a statement leaf for a section that does apply --
    is not available to a derived document either. A QOS summarising a
    section the dossier does not contain is its own kind of defect.

    Narratives are NOT passed in. Every context builder defaults its slots
    to None, so the derived documents see the data and never the prose --
    which is exactly the boundary described in this module's docstring.
    """
    # WHY this import is inside the function: this module sits ABOVE
    # `context`, not beside it -- a derived document is built out of other
    # sections' contexts. But `build_context` is also the single dispatcher
    # every section goes through, including 1.4.2 and 2.3, so it has to be
    # able to reach back here. That is a genuine cycle in the layering, and
    # the honest place to break it is at the higher layer: `context` imports
    # this module at the top like any other builder, and this module reaches
    # down for the dispatcher only when it is actually running.
    from app.templating.context import build_context

    contexts: dict[str, dict] = {}
    for instance in _module_3_instances(project):
        contexts[instance.key] = build_context(
            instance.number, project, narrative=None, subject=instance.subject
        )
    return contexts


def _module_3_instances(project) -> list[SectionInstance]:
    """The Module 3 instances a derived document may read from.

    WHY the filter is on the number rather than "everything expand_sections
    returns": a QIS/QOS derives from the BODY OF DATA. Reading 1.3.2's
    context to fill a QIS field would mean the summary of the quality
    dossier was quoting the label -- a real inversion, since the label is
    downstream of exactly this data (P23) and would make the two mutually
    derived with no source at all.

    3.2.R is excluded with them: its content comes from the region profile,
    not from the quality data, and nothing in a QIS or QOS summarises it.
    """
    return [
        instance
        for instance in expand_sections(project)
        if instance.number.startswith("3.2.") and not instance.number.startswith("3.2.R")
    ]


def context_for(contexts: dict[str, dict], key: str) -> dict:
    """The context for one instance, or a failure that says which is absent.

    Raising rather than returning `{}` is the same call `folder_for_section`
    makes: a derived document with a silently empty section is a document
    that looks finished and summarises nothing.
    """
    try:
        return contexts[key]
    except KeyError:
        raise KeyError(
            f"No rendered Module 3 context for {key!r}, so no derived document can "
            f"summarise it. Available: {', '.join(sorted(contexts))}"
        ) from None


def field(contexts: dict[str, dict], key: str, name: str, label: str) -> SourcedValue:
    """One derived field: a value lifted out of a Module 3 section context.

    `name` is a key of that context -- the same key the Module 3 template
    prints. That is the whole guarantee: if 3.2.P.3.2's batch size changes,
    this returns the new one, because there is no second place for it to be
    stored.
    """
    context = context_for(contexts, key)
    if name not in context:
        raise KeyError(
            f"Section {key} renders no field {name!r}, so nothing can be derived from "
            f"it. Its fields are: {', '.join(sorted(context))}"
        )
    return SourcedValue(label=label, value=_as_text(context[name]), source=key)


def rows(contexts: dict[str, dict], key: str, name: str) -> list:
    """A derived TABLE: a list of row dicts lifted whole from a context.

    Used where the derived document reproduces a Module 3 table rather than
    a single value -- the specification, the batch formula, the stability
    studies. Returned by reference on purpose: a copy would be a second
    list, and this module exists to make second copies impossible.
    """
    context = context_for(contexts, key)
    if name not in context:
        raise KeyError(
            f"Section {key} renders no table {name!r}. Its fields are: "
            f"{', '.join(sorted(context))}"
        )
    value = context[name]
    if not isinstance(value, list):
        raise TypeError(f"{key}.{name} is {type(value).__name__}, not a table of rows.")
    return value


def _as_text(value) -> str:
    """How a derived field prints.

    Deliberately dumb: a derived document must not reformat what Module 3
    already decided to print. "24 months" formatted here as "24" would be a
    second opinion about the same fact, which is the entire class of defect
    this module removes.
    """
    if value is None:
        return "[[NOT YET ON FILE]]"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        # A list of strings is a list of strings in both documents -- what
        # differs is only that a form prints it on one line. Joining is
        # presentation; it does not decide anything about the VALUES, which
        # is the line this function is careful about.
        return ", ".join(str(item) for item in value)
    return str(value)
