"""Programmatic Alembic upgrade hook.

Invoked from `src/main.py::lifespan` when `AUTO_MIGRATE=true` so the dev DB
schema is provisioned automatically on backend boot. Disable in environments
where migrations are run out-of-band (CI/CD, prod deploys) by setting
`AUTO_MIGRATE=false`.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from src.core.settings import Settings
from src.services.logger import get_logger

logger = get_logger("migrations")

# `alembic.ini` lives at the backend root: backend/alembic.ini
# This file is at:                          backend/src/core/migrations.py
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _build_alembic_config(settings: Settings) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return cfg


def _read_current_revision(settings: Settings) -> str | None:
    engine = create_engine(settings.DATABASE_URL)
    try:
        with engine.connect() as connection:
            ctx = MigrationContext.configure(connection)
            return ctx.get_current_revision()
    finally:
        engine.dispose()


def run_alembic_upgrade(settings: Settings) -> None:
    """Run `alembic upgrade head` against the configured DATABASE_URL.

    Idempotent — already-current databases finish in well under a second.
    Failures propagate to the caller (lifespan) so uvicorn exits non-zero.
    """
    cfg = _build_alembic_config(settings)
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    before = _read_current_revision(settings)

    if before == head:
        logger.info("Alembic: already at head %s, skipping upgrade", head)
        return

    logger.info("Alembic: upgrading from %s to %s", before, head)
    try:
        command.upgrade(cfg, "head")
    except Exception:
        logger.exception("Alembic upgrade failed")
        raise

    after = _read_current_revision(settings)
    logger.info("Alembic: migrated to %s", after)
