"""Alembic environment: async SQLite, batch mode for ALTER support."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from assistant.core.config import get_settings
from assistant.core.db import create_engine
from assistant.core.models import Base

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def _configure(connection: Connection | None = None) -> None:
    context.configure(
        connection=connection,
        url=None if connection is not None else _url(),
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
        literal_binds=connection is None,
    )


def run_migrations_offline() -> None:
    _configure()
    with context.begin_transaction():
        context.run_migrations()


def _check_foreign_keys(connection: Connection) -> None:
    broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if broken:
        tables = ", ".join(sorted({f"{row[0]} -> {row[2]}" for row in broken}))
        raise RuntimeError(f"migrations left rows with broken foreign keys in: {tables}")


def _run_sync(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()
        # Foreign keys are off while migrating, so nothing enforced them; check them now.
        _check_foreign_keys(connection)


async def run_migrations_online() -> None:
    # Foreign keys off: a batch table rebuild drops the old table, and with them on, that DROP
    # would cascade-delete every child row (e.g. all notes when `users` is rebuilt).
    engine = create_engine(_url(), foreign_keys=False)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync)
            await connection.commit()
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
