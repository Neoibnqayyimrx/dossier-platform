"""Render a P04 template context into plain text (P05).

The same context dict that fills a template's data slots (`app.templating.
context.build_context`) becomes, minus its `narrative` key, the block of
"facts the model must not contradict" in the generation prompt — and the
whitelist the numeric-leakage guardrail checks output against. One
function serves both, so there's only one place that decides what "the
facts" are.

WHY introspect via `sqlalchemy.inspect(...).mapper.column_attrs` rather
than walking `__dict__`: that gives exactly the mapped table columns (the
real, stored data) and nothing else — no relationships (which could cycle
back through a foreign key), no SQLAlchemy internal state, no need to know
in advance which fields a given model has.
"""

from __future__ import annotations

import enum

import sqlalchemy as sa

_BOOKKEEPING_COLUMNS = {"id", "created_at", "updated_at"}


def _is_model_instance(value: object) -> bool:
    return hasattr(type(value), "__mapper__")


def _is_business_field(key: str) -> bool:
    """Exclude primary/foreign keys and Base's audit columns -- internal
    database plumbing, never something a regulatory narrative should
    reference, and just noise in both the prompt and the numeric-leakage
    whitelist (a UUID is full of stray digit runs)."""
    return key not in _BOOKKEEPING_COLUMNS and not key.endswith("_id")


def _render_scalar(value: object) -> str:
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)


def _render_value(value: object) -> str:
    if value is None:
        return ""
    if _is_model_instance(value):
        mapper = sa.inspect(value).mapper
        fields = {
            attr.key: getattr(value, attr.key)
            for attr in mapper.column_attrs
            if _is_business_field(attr.key)
        }
        return "; ".join(
            f"{key}={_render_scalar(val)}" for key, val in fields.items() if val is not None
        )
    if isinstance(value, (list, tuple)):
        return "\n".join(f"- {_render_value(item)}" for item in value)
    return _render_scalar(value)


def render_facts(context: dict[str, object]) -> str:
    """Render every entry of `context` except `narrative` as a labeled,
    human-readable block."""
    sections = [
        f"{key}:\n{_render_value(value)}" for key, value in context.items() if key != "narrative"
    ]
    return "\n\n".join(sections)
