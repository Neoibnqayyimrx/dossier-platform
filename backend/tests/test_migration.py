"""Tests: the Alembic migration actually applies (and cleanly reverses).

Runs against a throwaway SQLite file rather than the live Postgres so this
stays fast and dependency-free in CI (no Postgres service defined there —
see .github/workflows/ci.yml). base.py's Uuid type and the SAEnum columns
are generic SQLAlchemy types that compile on both dialects; upgrading against
live Postgres is verified manually per the P01 definition of done.

WHY monkeypatch DATABASE_URL + clear the settings cache, instead of just
setting `sqlalchemy.url` on the Config passed to alembic: alembic/env.py
unconditionally does `config.set_main_option("sqlalchemy.url",
get_settings().database_url)`, so it always wins over anything set on the
Config object beforehand. get_settings() is process-wide @lru_cache'd, so we
must clear it after pointing DATABASE_URL at the tmp sqlite file, and clear
it again afterwards — otherwise this test runs migrations against whatever
real database Settings resolves to (verified the hard way: an earlier
version of this test dropped every table in the live dev Postgres).
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Every table the P01 migration creates — used to assert upgrade/downgrade
# actually did something, not just that alembic exited zero.
EXPECTED_TABLES = {
    "product",
    "manufacturer",
    "active_ingredient",
    "excipient",
    "packaging",
    "stability_study",
    "clinical_entry",
    "batch_formula_line",
    "project",
    "section",
    "sequence",
}


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_migration_upgrade_creates_all_tables(tmp_path, monkeypatch):
    db_file = tmp_path / "migration_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    assert get_settings().database_url == db_url  # guard: never let this hit a real DB
    try:
        command.upgrade(_alembic_config(db_url), "head")
    finally:
        get_settings.cache_clear()

    engine = sa.create_engine(f"sqlite:///{db_file}")
    tables = set(sa.inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= tables


def test_migration_downgrade_removes_all_tables(tmp_path, monkeypatch):
    db_file = tmp_path / "migration_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    assert get_settings().database_url == db_url  # guard: never let this hit a real DB
    try:
        command.upgrade(_alembic_config(db_url), "head")
        command.downgrade(_alembic_config(db_url), "base")
    finally:
        get_settings.cache_clear()

    engine = sa.create_engine(f"sqlite:///{db_file}")
    tables = set(sa.inspect(engine).get_table_names())
    assert not (EXPECTED_TABLES & tables)
