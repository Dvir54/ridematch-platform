"""Alembic environment: the URL always comes from `Settings.effective_database_url`.

So `uv run alembic upgrade head` migrates the dev database, and `APP_ENV=test uv run alembic
upgrade head` migrates `ridematch_test`.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import context
from app.config import get_settings
from app.db import create_engine
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.effective_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: object) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine: AsyncEngine = create_engine(settings)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
