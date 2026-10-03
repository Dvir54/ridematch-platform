"""Declarative base, engine/session factory and the request-scoped session dependency."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings
from app.ws_push import PUSHER_KEY


class Base(DeclarativeBase):
    """All models share this metadata; Alembic autogenerates against it."""


def create_engine(settings: Settings) -> AsyncEngine:
    """Engines are lazy, so this is safe to call outside a running event loop."""
    return create_async_engine(
        settings.effective_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args={"command_timeout": settings.db_command_timeout_seconds},
        future=True,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: routers serialize ORM objects after the service commits.
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        # Where `commit_and_push` finds the sender for what the transaction queued. Duck-typed
        # on purpose: `app.ws` imports the models, so importing it here would be a cycle.
        registry = getattr(request.app.state, "ws_registry", None)
        if registry is not None:
            session.info[PUSHER_KEY] = registry.push
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]
