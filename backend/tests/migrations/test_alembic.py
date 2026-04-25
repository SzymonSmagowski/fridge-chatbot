"""Migration test — `alembic upgrade head` → `downgrade base` → `upgrade head`.

Runs against a sandbox DB (`dev_alembic_test`) so the main test DB stays
clean. Verifies the migrations are reversible and converge.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


SANDBOX_DB = "dev_alembic_test"
ALEMBIC_INI = (
    Path(__file__).resolve().parents[2] / "alembic.ini"
)


@pytest.fixture
def sandbox_url() -> str:
    return f"postgresql+psycopg://postgres:postgres@postgres:5432/{SANDBOX_DB}"


@pytest.fixture(autouse=True)
def fresh_sandbox_db(sandbox_url: str):
    admin = create_engine(
        "postgresql+psycopg://postgres:postgres@postgres:5432/postgres",
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ),
            {"db": SANDBOX_DB},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SANDBOX_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{SANDBOX_DB}"'))
    yield
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ),
            {"db": SANDBOX_DB},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SANDBOX_DB}"'))
    admin.dispose()


def _config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _table_names(url: str) -> set[str]:
    eng = create_engine(url)
    try:
        return set(inspect(eng).get_table_names())
    finally:
        eng.dispose()


@pytest.fixture
def alembic_env(monkeypatch):
    """Point the Alembic env at the sandbox DB without modifying env.py.

    `alembic/env.py` reads `Settings().DATABASE_URL` directly, which Settings
    builds from env vars. We temporarily swap POSTGRES_DB so env.py lands on
    the sandbox instead of `dev_test`.
    """
    monkeypatch.setenv("POSTGRES_DB", SANDBOX_DB)
    # Invalidate any cached settings singletons.
    from src.core import dependencies as deps
    deps.get_settings.cache_clear()
    yield
    deps.get_settings.cache_clear()


def test_alembic_upgrade_head_creates_expected_tables(
    sandbox_url: str, alembic_env
) -> None:
    cfg = _config(sandbox_url)
    command.upgrade(cfg, "head")
    tables = _table_names(sandbox_url)
    # Spot-check the 13 new domain tables + legacy ones exist.
    expected = {
        "families",
        "family_preferences",
        "devices",
        "members",
        "google_tokens",
        "calendar_sync_state",
        "cars",
        "labels",
        "note_labels",
        "notes",
        "note_cars",
        "events",
        "event_targets",
        "event_cars",
        "external_events_cache",
        # Legacy tables — must survive upgrades (chat threads).
        "users",
        "threads",
        "messages",
    }
    missing = expected - tables
    assert missing == set(), f"alembic upgrade head missing: {missing}"


def test_alembic_upgrade_then_downgrade_then_upgrade_is_idempotent(
    sandbox_url: str, alembic_env
) -> None:
    cfg = _config(sandbox_url)
    command.upgrade(cfg, "head")
    after_first = _table_names(sandbox_url)

    command.downgrade(cfg, "base")
    after_downgrade = _table_names(sandbox_url)
    # Downgrade intentionally preserves legacy users/threads/messages (see
    # 0001_initial_schema.py — they're retained for chat FKs); everything in
    # the new family-scoped schema must be gone.
    leftover_family_tables = after_downgrade - {
        "alembic_version",
        "users",
        "threads",
        "messages",
    }
    assert leftover_family_tables == set(), (
        f"Downgrade left family-scoped tables behind: {leftover_family_tables}"
    )

    command.upgrade(cfg, "head")
    after_second = _table_names(sandbox_url)
    assert after_second == after_first
