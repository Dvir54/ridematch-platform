"""`GET /health` (liveness) and `GET /ready` (readiness): the endpoints that need no token.

`/health` touches nothing external, so a database outage never turns into a restart loop.
`/ready` is what the host gates deploys on: the database decides it, Redis is only reported.
"""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.errors import AppError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

DB_TIMEOUT_SECONDS = 2.0
REDIS_TIMEOUT_SECONDS = 1.0


class Health(BaseModel):
    status: Literal["ok"]


class Ready(BaseModel):
    status: Literal["ready"]
    db: Literal[True]
    redis: bool


class NotReady(AppError):
    status_code = 503
    default_code = "NOT_READY"
    default_message = "Database unreachable."


@router.get("/health", response_model=Health, summary="Liveness: the process serves HTTP")
async def health() -> Health:
    return Health(status="ok")


async def _db_ok(engine: AsyncEngine) -> bool:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True


@router.get("/ready", response_model=Ready, summary="Readiness: the database is reachable")
async def ready(request: Request) -> Ready:
    try:
        await asyncio.wait_for(_db_ok(request.app.state.engine), DB_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning("Readiness: database unreachable (%s)", type(exc).__name__)
        raise NotReady(details=[{"field": "db", "message": "Database unreachable."}]) from exc

    redis_ok = True
    redis: Redis = request.app.state.redis
    try:
        await asyncio.wait_for(redis.ping(), REDIS_TIMEOUT_SECONDS)
    except Exception as exc:
        redis_ok = False
        logger.warning("Readiness: Redis unreachable (%s)", type(exc).__name__)

    return Ready(status="ready", db=True, redis=redis_ok)
