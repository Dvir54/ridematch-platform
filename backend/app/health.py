"""`GET /health` — the one endpoint that needs no token."""

import logging
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from app.db import DbSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    db: bool
    redis: bool


@router.get("/health", response_model=Health, summary="Liveness check (DB + Redis reachable)")
async def health(request: Request, db: DbSession) -> Health:
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        logger.warning("Health check: database unreachable (%s)", exc)

    redis_ok = True
    redis: Redis = request.app.state.redis
    try:
        await redis.ping()
    except Exception as exc:
        redis_ok = False
        logger.warning("Health check: Redis unreachable (%s)", exc)

    return Health(status="ok" if db_ok and redis_ok else "degraded", db=db_ok, redis=redis_ok)
