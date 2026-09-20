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

import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Every table the P01 + P02 migrations create — used to assert upgrade/
# downgrade actually did something, not just that alembic exited zero.
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
    "user",
    "kb_document",
    "kb_chunk",
    "narrative_generation",
    "narrative_generation_source",
    "certificate",
    "validation_override",
    "applicant",
    "declaration",
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


def test_the_p26_migration_backfills_a_version_for_every_existing_document(tmp_path, monkeypatch):
    """The backfill, asserted against a row that predates the version table.

    WHY this needs its own test rather than riding on the upgrade test
    above: "the table exists" and "the data that was already there is
    correctly represented in it" are different claims, and only the second
    one is what makes a migration safe to run on a real database. A leaf
    whose history began at version 2 would read as though version 1 had
    been lost -- it had not; it is the file currently attached.
    """
    db_file = tmp_path / "backfill_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()

    try:
        # Stop one revision BEFORE the version table exists, so the
        # section_document row we insert is genuinely a pre-P26 row.
        command.upgrade(_alembic_config(db_url), "f5c8b21a90d7")

        engine = sa.create_engine(f"sqlite:///{db_file}")
        with engine.begin() as conn:
            user_id = str(uuid.uuid4())
            product_id = str(uuid.uuid4())
            project_id = str(uuid.uuid4())
            document_id = str(uuid.uuid4())
            stamp = "2026-03-01 09:00:00"
            conn.execute(
                sa.text(
                    "INSERT INTO user (id, email, hashed_password, role, is_active,"
                    " created_at, updated_at) VALUES (:i, :e, 'x', 'USER', 1, :t, :t)"
                ),
                {"i": user_id, "e": "filer@example.com", "t": stamp},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO product (id, brand_name, generic_name, owner_id,"
                    " created_at, updated_at) VALUES (:i, 'EXAMOX', 'Amoxicillin', :o, :t, :t)"
                ),
                {"i": product_id, "o": user_id, "t": stamp},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO project (id, name, product_id, region,"
                    " created_at, updated_at)"
                    " VALUES (:i, 'EXAMOX NAFDAC', :p, 'NAFDAC', :t, :t)"
                ),
                {"i": project_id, "p": product_id, "t": stamp},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO section_document (id, project_id, section_number,"
                    " subject_slug, storage_key, md5, size_bytes, original_filename,"
                    " content_type, uploaded_by_id, uploaded_at, created_at, updated_at)"
                    " VALUES (:i, :p, '1.2.7', '', :k, :m, 1234, 'CPP_March.pdf',"
                    " 'application/pdf', :u, :t, :t, :t)"
                ),
                {
                    "i": document_id,
                    "p": project_id,
                    "k": f"projects/{project_id}/documents/1.2.7.pdf",
                    "m": "0" * 32,
                    "u": user_id,
                    "t": stamp,
                },
            )
        engine.dispose()

        command.upgrade(_alembic_config(db_url), "head")

        engine = sa.create_engine(f"sqlite:///{db_file}")
        with engine.begin() as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT version_number, storage_key, md5, size_bytes,"
                    " original_filename, uploaded_by_id FROM document_version"
                    " WHERE section_document_id = :d"
                ),
                {"d": document_id},
            ).all()
        engine.dispose()

        assert len(rows) == 1, "exactly one version per pre-existing document"
        (version,) = rows
        assert version.version_number == 1
        assert version.original_filename == "CPP_March.pdf"
        assert version.md5 == "0" * 32
        assert version.size_bytes == 1234
        assert version.uploaded_by_id == user_id
        # The key is left at the PRE-P26 deterministic path on purpose: the
        # bytes really are there, under really that key. Rewriting it to
        # look like the new per-version convention would put a false
        # statement in the audit trail this table exists to provide.
        assert version.storage_key == f"projects/{project_id}/documents/1.2.7.pdf"
    finally:
        get_settings.cache_clear()
