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


# ---------------------------------------------------------------------------
# Spot-checks for the new 0005 + 0006 migrations (Tier B/11 in the orch brief)
# ---------------------------------------------------------------------------


def _index_names(url: str, table: str) -> set[str]:
    eng = create_engine(url)
    try:
        return {idx["name"] for idx in inspect(eng).get_indexes(table)}
    finally:
        eng.dispose()


def test_alembic_0005_creates_messages_pagination_index(
    sandbox_url: str, alembic_env
) -> None:
    cfg = _config(sandbox_url)
    command.upgrade(cfg, "head")
    indexes = _index_names(sandbox_url, "messages")
    assert "ix_messages_thread_created_id" in indexes, (
        f"messages pagination composite index missing; have: {indexes}"
    )


def test_alembic_0006_creates_feedback_table_with_expected_indexes(
    sandbox_url: str, alembic_env
) -> None:
    cfg = _config(sandbox_url)
    command.upgrade(cfg, "head")
    tables = _table_names(sandbox_url)
    assert "feedback" in tables
    indexes = _index_names(sandbox_url, "feedback")
    expected = {
        "ix_feedback_family_id",
        "ix_feedback_family_created",
        "ix_feedback_family_status",
    }
    assert expected.issubset(indexes), (
        f"feedback table missing expected indexes: have {indexes}, "
        f"need {expected}"
    )


def test_alembic_0006_creates_three_feedback_enums(
    sandbox_url: str, alembic_env
) -> None:
    cfg = _config(sandbox_url)
    command.upgrade(cfg, "head")
    eng = create_engine(sandbox_url)
    try:
        with eng.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT typname FROM pg_type "
                    "WHERE typname IN ("
                    "'feedback_category','feedback_author_kind','feedback_status'"
                    ")"
                )
            ).all()
            names = {r[0] for r in rows}
    finally:
        eng.dispose()
    assert names == {
        "feedback_category",
        "feedback_author_kind",
        "feedback_status",
    }, f"Expected 3 feedback enums in pg_type, got: {names}"


def test_alembic_downgrading_past_0006_drops_feedback_table_and_enums(
    sandbox_url: str, alembic_env
) -> None:
    """Down-migration must drop both the table AND the supporting enums.
    Otherwise a re-upgrade would fail with `type already exists`.
    """
    cfg = _config(sandbox_url)
    command.upgrade(cfg, "head")
    # Verify pre-state.
    assert "feedback" in _table_names(sandbox_url)

    # Step down ONE migration (back to 0005). 0006 down() drops table + enums.
    command.downgrade(cfg, "0005_messages_pagination_index")
    after = _table_names(sandbox_url)
    assert "feedback" not in after, (
        "0006 downgrade did not drop the feedback table"
    )

    eng = create_engine(sandbox_url)
    try:
        with eng.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT typname FROM pg_type "
                    "WHERE typname IN ("
                    "'feedback_category','feedback_author_kind','feedback_status'"
                    ")"
                )
            ).all()
            leftover_enums = {r[0] for r in rows}
    finally:
        eng.dispose()
    assert leftover_enums == set(), (
        "0006 downgrade left feedback enums behind in pg_type: "
        f"{leftover_enums}"
    )

    # Re-upgrade must succeed (idempotent).
    command.upgrade(cfg, "head")
    assert "feedback" in _table_names(sandbox_url)
