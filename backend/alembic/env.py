"""Alembic environment.

Imports `Base` from src.db.postgres + every model module so
`target_metadata.tables` is fully populated for autogenerate. URL is taken from
our `Settings` (the same config the app uses) instead of `alembic.ini` so the
backend stays single-source-of-truth on the DB connection.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `src` importable regardless of where alembic is invoked from.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.settings import Settings  # noqa: E402
from src.db.postgres import Base  # noqa: E402
import src.models  # noqa: E402, F401 — registers every table on Base.metadata

config = context.config

# Inject the runtime DATABASE_URL (overrides whatever's in alembic.ini).
config.set_main_option("sqlalchemy.url", Settings().DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
