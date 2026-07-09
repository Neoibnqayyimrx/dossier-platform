"""End-to-end demo of the vertical slice: model -> template -> validate.

Run: python run_demo.py

It seeds the real (buggy) LAMOX 3.2.P.1, persists to an in-memory SQLite DB via
the real SQLAlchemy models, runs the deterministic rule engine, and prints the
report. Then it seeds the corrected version and shows a clean pass. Finally it
renders 3.2.P.1 from structured data to show the bugs can't survive templating.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Project
import app.validation.rules  # noqa: F401 -- importing registers the rules
from app.validation.engine import run_all, Severity
from app.seed.lamox import build_lamox
from app.templating.section_map import render_p1


def _persist_and_load(buggy: bool) -> tuple[Session, Project]:
    """Use the REAL models against SQLite so this exercises the actual schema."""
    engine = create_engine("sqlite://")  # in-memory
    Base.metadata.create_all(engine)
    session = Session(engine)
    project = build_lamox(buggy=buggy)
    session.add(project)
    session.commit()
    session.refresh(project)
    return session, project


def _print_report(title: str, report) -> None:
    print(f"\n{'='*70}\n{title}\n{'='*70}")
    if not report.findings:
        print("  No findings.")
    for f in report.findings:
        mark = {"ERROR": "X", "WARNING": "!", "INFO": "i"}[f.severity.value]
        loc = f" [{f.section}]" if f.section else ""
        print(f"  [{mark}] {f.rule_id} ({f.severity.value}){loc}: {f.message}")
    print(f"\n  Exportable (no errors)? {report.is_exportable}")
    print(f"  Errors: {len(report.errors)}  |  Total findings: {len(report.findings)}")


def main() -> None:
    # 1) The real dossier, as submitted (with its real defects)
    session, project = _persist_and_load(buggy=True)
    report = run_all(project)
    _print_report("LAMOX as submitted (real dossier content)", report)

    # 2) After fixing the three copy-paste defects
    session2, fixed = _persist_and_load(buggy=False)
    report2 = run_all(fixed)
    _print_report("LAMOX after corrections", report2)

    # 3) Show that templating from structured data can't reproduce the bugs
    print(f"\n{'='*70}\n3.2.P.1 rendered from structured data (P04)\n{'='*70}")
    print(render_p1(fixed.product))


if __name__ == "__main__":
    main()
