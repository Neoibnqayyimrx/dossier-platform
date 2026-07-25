"""Tests for app.narrative.facts.render_facts: the same rendering that
becomes both the LLM prompt's FACTS block and the numeric-leakage
whitelist, so it needs to include real data values and exclude database
bookkeeping (ids, timestamps, foreign keys) that would just add noise."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.narrative.facts import render_facts
from app.seed.examox import build_examox
from app.templating.context import build_context


def _project():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    project = build_examox(buggy=False)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def test_render_facts_includes_real_data_values():
    context = build_context("3.2.P.8.1", _project())
    text = render_facts(context)
    assert "EXAMOX" in text
    assert "24" in text  # shelf_life_months
    assert "30C/65%RH" in text  # stability study condition


def test_render_facts_excludes_bookkeeping_columns():
    context = build_context("3.2.P.1", _project())
    text = render_facts(context)
    assert "id=" not in text
    assert "created_at" not in text
    assert "product_id" not in text


def test_render_facts_excludes_the_narrative_key():
    context = build_context("3.2.P.1", _project(), narrative={"description": "should not appear"})
    text = render_facts(context)
    assert "should not appear" not in text
